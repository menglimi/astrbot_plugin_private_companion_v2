from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.foundation.refs import SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.relationships.codec import memory_from_json, memory_json
from companion_v2.relationships.management import RelationshipMemoryManagement
from companion_v2.relationships.models import RelationshipMemoryState as State
from companion_v2.relationships.service import RelationshipMemoryService
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import INSTALLATION, NOW, SCOPE
from tests.test_relationship_context import remember


class RelationshipManagementTests(MessageFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.service = RelationshipMemoryService(self.runtime, now=self.clock.now)
        self.manager = RelationshipMemoryManagement(self.service)

    def memory(self, identifier="memory-a", *, context=None, source=None, state=State.PROPOSED):
        context = context or self.context
        source = source or self.event("source-" + identifier, context=context).source
        return remember(self.service, context, source, identifier=identifier, state=state)

    def listing(self, **changes):
        return self.manager.list(**(dict(operator=self.core, context=self.context) | changes))

    def command(self, item, action, **changes):
        return self.manager.command(**(dict(operator=self.core, context=self.context, memory_id=item["memory_id"],
            action=action, expected_revision=item["revision"], view_token=item["view_token"],
            operation_key=f'{action}:{item["revision"]}') | changes))

    def test_review_adopt_correct_and_retract_record_actual_administrator(self):
        original = self.memory()
        item = self.listing().unwrap()["items"][0]
        self.assertEqual(item["actions"], ["review", "revise", "retract"])
        item = self.command(item, "review").unwrap()["item"]
        self.assertEqual(item["attribution"]["reviewed_by"], self.core.subject.subject_id)
        item = self.command(item, "adopt").unwrap()["item"]
        self.assertEqual(item["attribution"]["adopted_by"], self.core.subject.subject_id)
        self.assertEqual(self.service.adopted_for_relationship(actor=self.important, scope=SCOPE).unwrap()[0].memory_id,
                         original.memory_id)
        item = self.command(item, "revise", interpretation="更正：只是那一天的感受。").unwrap()["item"]
        self.assertEqual(item["state"], "proposed")
        self.assertEqual(item["attribution"]["revised_by"], self.core.subject.subject_id)
        self.assertIsNone(item["attribution"]["adopted_by"])
        self.assertEqual(self.service.adopted_for_relationship(actor=self.important, scope=SCOPE).unwrap(), ())
        item = self.command(item, "retract").unwrap()["item"]
        self.assertEqual(item["actions"], [])
        self.assertEqual(item["attribution"]["retracted_by"], self.core.subject.subject_id)
        records = self.service.revisions(original.memory_id, actor=self.important, scope=SCOPE).unwrap()
        self.assertEqual(len(records), 5)
        self.assertEqual(records[0].interpretation, original.interpretation)

    def test_repeated_operation_keeps_original_receipt_and_returns_current_version(self):
        self.memory()
        proposed = self.listing().unwrap()["items"][0]
        first = self.command(proposed, "review").unwrap()
        self.assertEqual(self.command(proposed, "review").unwrap(), first)
        adopted = self.command(first["item"], "adopt").unwrap()["item"]
        replay = self.command(proposed, "review").unwrap()
        self.assertEqual(replay["applied_revision"], 2)
        self.assertEqual(replay["item"], adopted)
        conflict = self.command(adopted, "revise", interpretation="另一个请求", operation_key="review:1")
        self.assertFalse(conflict.is_success)
        self.assertEqual(self.listing().unwrap()["items"][0]["revision"], 3)

    def test_two_connections_cannot_apply_different_corrections_to_one_version(self):
        self.memory()
        item = self.listing().unwrap()["items"][0]
        other = RelationshipMemoryManagement(RelationshipMemoryService(self.open_runtime(), now=self.clock.now))
        def update(pair):
            manager, text = pair
            return manager.command(operator=self.core, context=self.context, memory_id=item["memory_id"],
                action="revise", expected_revision=item["revision"], view_token=item["view_token"],
                operation_key=text, interpretation=text)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(update, ((self.manager, "更正甲"), (other, "更正乙"))))
        self.assertEqual(sum(result.is_success for result in results), 1)
        self.assertEqual(self.listing().unwrap()["items"][0]["revision"], 2)

    def test_revoked_source_redacts_body_but_still_allows_attributed_retraction(self):
        memory = self.memory(state=State.ADOPTED)
        self.messages.sources.revoke(memory.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        item = self.listing().unwrap()["items"][0]
        self.assertIsNone(item["interpretation"])
        self.assertEqual(item["unavailable_reason"], "source_revoked")
        self.assertEqual(item["actions"], ["retract"])
        self.assertEqual(self.command(item, "revise", interpretation="不应恢复来源").failure.code, "source_revoked")
        result = self.command(item, "retract").unwrap()["item"]
        self.assertEqual(result["state"], "retracted")
        self.assertIsNone(result["interpretation"])

    def test_expiry_between_view_and_adoption_is_rechecked(self):
        source = self.event("short", expires_at=NOW + timedelta(seconds=1)).source
        self.memory(source=source, state=State.REVIEWED)
        item = self.listing().unwrap()["items"][0]
        self.clock.advance(timedelta(seconds=2))
        self.assertEqual(self.command(item, "adopt").failure.code, "source_expired")

    def test_ordinary_participant_cannot_use_administrator_surface(self):
        self.memory()
        self.assertEqual(self.listing(operator=self.important).failure.code, "core_access_required")
        item = self.listing().unwrap()["items"][0]
        self.assertEqual(self.command(item, "review", operator=self.important).failure.code, "core_access_required")

    def test_downgrade_or_rebinding_fences_an_open_admin_view(self):
        self.memory()
        item = self.listing().unwrap()["items"][0]
        self.policy.set_tier(self.core.subject, AuthorizationTier.IMPORTANT,
                             expected_revision=self.policy.revision, observed_at=NOW)
        self.assertEqual(self.command(item, "review").failure.code, "core_access_required")
        self.identity.revoke_binding(self.core.binding_id, expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertEqual(self.listing().failure.code, "binding_revoked")

    def test_changed_persona_or_target_cannot_reuse_an_open_view(self):
        self.memory()
        item = self.listing().unwrap()["items"][0]
        foreign = self.context_for(self.standard)
        self.assertEqual(self.command(item, "review", context=foreign).failure.code, "relationship_view_stale")
        current = self.personas.binding("base")
        role = SubjectRef(INSTALLATION, SubjectKind.BOT, "other-role")
        self.personas.set_binding(replace(current, revision=current.revision + 1, role=role),
                                  expected_revision=current.revision, observed_at=NOW)
        self.assertEqual(self.command(item, "review").failure.code, "relationship_target_changed")

    def test_pagination_filters_full_scope_and_states_before_limiting(self):
        other = self.context_for(self.important, replace(SCOPE, native_scope_id="other", conversation_id="other", session_id="other"))
        self.memory("00-other-scope", context=other)
        for name in ("a", "b", "c"):
            self.memory(name)
        self.memory("d-adopted", state=State.ADOPTED)
        first = self.listing(limit=2, state="proposed").unwrap()
        self.assertEqual([item["memory_id"] for item in first["items"]], ["a", "b"])
        second = self.listing(limit=2, state="proposed", after_id=first["next_cursor"]).unwrap()
        self.assertEqual([item["memory_id"] for item in second["items"]], ["c"])
        self.assertIsNone(second["next_cursor"])

    def test_invalid_commands_and_early_adoption_do_not_mutate_records(self):
        self.memory()
        item = self.listing().unwrap()["items"][0]
        for changes in ({"expected_revision": True}, {"view_token": "other"}, {"operation_key": ""},
                        {"interpretation": "cannot alter text while reviewing"}):
            with self.subTest(changes=changes):
                self.assertFalse(self.command(item, "review", **changes).is_success)
        self.assertFalse(self.command(item, "adopt").is_success)
        self.assertEqual(self.listing().unwrap()["items"][0]["revision"], 1)

    def test_old_records_restore_without_inventing_a_correction_actor(self):
        original = self.memory()
        old = json.loads(memory_json(original))
        old.pop("revised_by")
        self.assertEqual(memory_from_json(json.dumps(old)), original)
