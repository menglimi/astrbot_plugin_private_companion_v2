"""Explicit Dashboard growth management stays core-authorized and revisioned."""

from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.role_work.growth import GrowthKind, PersistentRoleGrowthLedger, RoleGrowthManagement, RoleGrowthRecord
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from astrbot_host.management_identity import dashboard_operator
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import NOW, SCOPE


class RoleGrowthManagementTests(MessageFixture):
    def setUp(self):
        super().setUp()
        self.ledger = PersistentRoleGrowthLedger(self.runtime, now=self.clock.now)
        self.management = RoleGrowthManagement(self.ledger)
        self.operator = dashboard_operator(self.runtime, "growth-admin", at=NOW)
        self.evidence = self.event("growth-management-evidence").source

    def create(self, **changes):
        values = dict(operator=self.operator, context=self.context, operation_key="create-one",
            view_token=self.management.list(operator=self.operator, context=self.context).unwrap()["create_token"],
            kind=GrowthKind.GOAL, title="学习水彩构图", description="每周练习一幅小画。",
            progress_note="刚整理好参考资料。", sources=(self.evidence,))
        return self.management.create(**(values | changes)).unwrap()

    def command(self, item, action, key, **changes):
        return self.management.command(operator=self.operator, context=self.context,
            growth_id=item["growth_id"], expected_revision=item["revision"],
            view_token=item["view_token"], operation_key=key, action=action, **changes).unwrap()

    def test_create_confirm_revise_pause_resume_complete_and_receipts(self):
        proposed = self.create()["item"]
        self.assertEqual(proposed["state"], "proposed")
        replay = self.create()
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["item"]["growth_id"], proposed["growth_id"])

        active = self.command(proposed, "confirm", "confirm-one")["item"]
        self.assertEqual((active["revision"], active["state"], active["confirmed_by"]),
                         (2, "active", self.operator.subject.subject_id))
        pause_receipt = self.command(active, "pause", "pause-one")
        self.assertEqual(pause_receipt["item"]["state"], "paused")
        replay = self.command(active, "pause", "pause-one")
        self.assertEqual(replay, pause_receipt)

        paused = pause_receipt["item"]
        active_again = self.command(paused, "resume", "resume-one")["item"]
        revised = self.command(active_again, "revise", "revise-one", title="练习水彩光影",
            description="在周末继续练习。", progress_note="下一步尝试不同光线。",
            sources=(self.evidence,))["item"]
        self.assertEqual((revised["revision"], revised["state"], revised["title"]),
                         (5, "proposed", "练习水彩光影"))
        active_after_revision = self.command(revised, "confirm", "confirm-two")["item"]
        achieved = self.command(active_after_revision, "complete", "complete-one")["item"]
        self.assertEqual(achieved["state"], "achieved")
        self.assertNotIn("revise", achieved["actions"])

    def test_skill_cannot_be_completed_and_retired_record_is_read_only(self):
        result = self.create(operation_key="create-skill", kind=GrowthKind.SKILL, title="学习速写")
        active = self.command(result["item"], "confirm", "confirm-skill")["item"]
        self.assertNotIn("complete", active["actions"])
        denied = self.management.command(operator=self.operator, context=self.context,
            growth_id=active["growth_id"], expected_revision=active["revision"], view_token=active["view_token"],
            operation_key="complete-skill", action="complete")
        self.assertEqual(denied.failure.code, "growth_command_conflict")
        retired = self.command(active, "retire", "retire-skill")["item"]
        self.assertEqual(retired["state"], "retired")
        self.assertEqual(retired["actions"], [])

    def test_dashboard_operator_requires_current_core_tier_and_target(self):
        policy = ObjectAccessPolicy(self.runtime)
        policy.set_tier(self.operator.subject, AuthorizationTier.STANDARD,
                        expected_revision=policy.revision, observed_at=NOW)
        result = self.management.list(operator=self.operator, context=self.context)
        self.assertEqual(result.failure.code, "core_access_required")

    def test_unavailable_evidence_hides_text_but_allows_retirement(self):
        self.create()
        self.management.sources.revoke(self.evidence, expected_governance_revision=1, observed_at=NOW).unwrap()
        listed = self.management.list(operator=self.operator, context=self.context).unwrap()["items"][0]
        self.assertEqual(listed["unavailable_reason"], "source_revoked")
        self.assertIsNone(listed["title"])
        self.assertIn("retire", listed["actions"])
        retired = self.command(listed, "retire", "retire-unavailable")["item"]
        self.assertEqual(retired["state"], "retired")

    def test_stale_view_token_and_cross_scope_record_do_not_mutate(self):
        proposed = self.create()["item"]
        self.assertEqual(self.management.command(operator=self.operator, context=self.context,
            growth_id=proposed["growth_id"], expected_revision=proposed["revision"], view_token="wrong",
            operation_key="stale", action="confirm").failure.code, "growth_view_stale")
        other_context = self.context_for(self.standard)
        other_source = self.event("other-scope-evidence", context=other_context).source
        other_owner = RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, other_context.role_binding.role.subject_id)
        self.ledger.add(RoleGrowthRecord(
            "other-scope-growth", other_owner, other_context.scope, GrowthKind.GOAL, "另一个会话中的目标", "", "",
            (other_source,), NOW, NOW, proposed_by=self.standard.subject))
        result = self.management.list(operator=self.operator, context=self.context, limit=1).unwrap()
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["growth_id"], proposed["growth_id"])
        self.assertIsNone(result["next_cursor"])

    def test_proposal_replay_after_revision_and_restart_returns_current_governed_view(self):
        proposed = self.create()["item"]
        revised = self.command(proposed, "revise", "correction", title="更正后的目标",
            description="保留新的表述。", progress_note="仍是提案。", sources=None)["item"]
        self.clock.advance(timedelta(seconds=2))
        runtime = self.open_runtime()
        self.management = RoleGrowthManagement(PersistentRoleGrowthLedger(runtime, now=self.clock.now))
        replay = self.create()
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["applied_revision"], 1)
        self.assertEqual(replay["item"], revised)
        self.assertEqual(len(self.ledger.revisions(proposed["growth_id"], owner=self.reader_owner())), 2)
        with self.assertRaisesRegex(RuntimeError, "idempotency_key_conflict"):
            self.create(title="不能复用原操作号写别的目标")

    def reader_owner(self):
        return RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, self.context.role_binding.role.subject_id)

    def test_old_revision_cannot_overwrite_and_replay_does_not_return_old_body(self):
        proposed = self.create()["item"]
        active = self.command(proposed, "confirm", "confirm")["item"]
        revised = self.command(active, "revise", "revise", title="新标题", description="",
                               progress_note="", sources=None)["item"]
        replay = self.command(proposed, "confirm", "confirm")
        self.assertEqual(replay["applied_revision"], 2)
        self.assertEqual(replay["item"], revised)
        with self.assertRaisesRegex(RuntimeError, "growth_command_conflict"):
            self.command(active, "pause", "stale-pause")
        with self.assertRaisesRegex(RuntimeError, "idempotency_key_conflict"):
            self.command(proposed, "retire", "confirm")

    def test_revision_replay_keeps_original_default_sources_after_another_revision(self):
        proposed = self.create()["item"]
        arguments = dict(title="第一轮修订", description="", progress_note="")
        first = self.command(proposed, "revise", "first", **arguments)["item"]
        replacement = self.event("new-source").source
        second = self.command(first, "revise", "second", title="第二轮修订", description="",
                              progress_note="", sources=(replacement,))["item"]
        replay = self.command(proposed, "revise", "first", **arguments)
        self.assertEqual(replay["applied_revision"], first["revision"])
        self.assertEqual(replay["item"], second)

    def test_rejected_sources_leave_no_partial_proposal_or_receipt(self):
        original_count = self.runtime.read_one("SELECT COUNT(*) n FROM operations", ())["n"]
        other_context = self.context_for(self.standard)
        wrong_scope = self.event("wrong-scope", context=other_context).source
        for sources in ((), (self.evidence, self.evidence), (wrong_scope,),
                        (replace(self.evidence, owner="forged"),), ("not-a-source",)):
            with self.subTest(sources=sources), self.assertRaises(RuntimeError):
                self.create(sources=sources)
        self.assertEqual(self.ledger.for_role(self.reader_owner()), ())
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM operations", ())["n"], original_count)

    def test_revoked_operator_and_changed_target_are_not_reprovisioned(self):
        self.create()
        self.identity.revoke_binding(self.operator.binding_id, revoked_at=NOW,
                                     expected_revision=self.identity.revision)
        result = self.management.list(operator=self.operator, context=self.context)
        self.assertEqual(result.failure.code, "binding_revoked")
        current = self.personas.binding("base")
        self.personas.set_binding(replace(current, revision=current.revision + 1),
            expected_revision=current.revision, observed_at=NOW)
        result = self.management.list(operator=self.core, context=self.context)
        self.assertEqual(result.failure.code, "growth_target_changed")

    def test_revoked_sources_cannot_confirm_but_can_be_replaced_by_explicit_revision(self):
        proposed = self.create()["item"]
        self.management.sources.revoke(self.evidence, expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaisesRegex(RuntimeError, "source_revoked"):
            self.command(proposed, "confirm", "confirm-denied")
        revised = self.command(proposed, "revise", "new-evidence", title="有新依据的提案",
            description="", progress_note="", sources=(self.event("replacement").source,))["item"]
        self.assertEqual(revised["state"], "proposed")
        self.assertIsNone(revised["confirmed_by"])
        self.assertEqual(self.command(revised, "withdraw", "withdraw")["item"]["state"], "retired")

    def test_two_connections_cannot_apply_competing_corrections_to_one_revision(self):
        proposed = self.create()["item"]
        managers = (self.management, RoleGrowthManagement(PersistentRoleGrowthLedger(self.open_runtime(), now=self.clock.now)))
        def revise(index):
            return managers[index].command(operator=self.operator, context=self.context,
                growth_id=proposed["growth_id"], expected_revision=1, view_token=proposed["view_token"],
                operation_key="competing-" + str(index), action="revise", title="修订 " + str(index),
                description="", progress_note="", sources=(self.evidence,))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(revise, (0, 1)))
        self.assertEqual(sum(result.is_success for result in results), 1)
        self.assertEqual(next(result.failure.code for result in results if not result.is_success), "growth_command_conflict")
        self.assertEqual(len(self.ledger.revisions(proposed["growth_id"], owner=self.reader_owner())), 2)

    def test_management_view_cannot_be_carried_to_another_private_scope(self):
        proposed = self.create()["item"]
        other_context = self.context_for(self.standard)
        result = self.management.command(operator=self.operator, context=other_context,
            growth_id=proposed["growth_id"], expected_revision=1, view_token=proposed["view_token"],
            operation_key="cross-user", action="confirm")
        self.assertEqual(result.failure.code, "growth_view_stale")
        self.assertEqual(self.management.list(operator=self.operator, context=other_context).unwrap()["items"], [])
