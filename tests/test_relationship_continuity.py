"""A private conversation reset preserves relationships only under original authority."""

from dataclasses import replace
import unittest

from companion_v2.conversation.relationship_context import RelationshipContext
from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import ScopeKind, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.personas import PersonaBinding, SelectorKind
from companion_v2.relationships.management import RelationshipMemoryManagement
from companion_v2.relationships.service import RelationshipMemoryService
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import INSTALLATION, NOW, SCOPE
from tests.test_relationship_context import remember


class RelationshipContinuityTests(MessageFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.service = RelationshipMemoryService(self.runtime, now=self.clock.now)
        self.consumer = RelationshipContext(self.service)
        self.memory = remember(self.service, self.context, self.event("original-evidence").source)
        self.reset = self.context_for(self.important,
            replace(SCOPE, conversation_id="conversation-reset", session_id="session-reset"))

    def test_reset_retains_original_sources_and_revision_without_rewriting_scope(self):
        snapshot = self.consumer.capture(self.reset, NOW)
        self.assertEqual(snapshot["references"], [{"memory_id": self.memory.memory_id, "revision": self.memory.revision}])
        materials = self.consumer.contributions(snapshot, self.reset, NOW)
        self.assertEqual(len(materials), 1)
        original = self.service.read(self.memory.memory_id, actor=self.reset.actor, scope=self.reset.scope).unwrap()
        self.assertEqual(original, self.memory)
        self.assertEqual(original.sources[0].scope, SCOPE)
        self.assertEqual(original.scope, SCOPE)

    def test_historical_grant_must_remain_valid_as_well_as_current_grant(self):
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                             expected_revision=self.policy.revision, observed_at=NOW)
        historic = self.grant(self.important, SCOPE, "relationship.memory.read")
        self.grant(self.important, self.reset.scope, "relationship.memory.read")
        snapshot = self.consumer.capture(self.reset, NOW)
        self.assertEqual(len(snapshot["references"]), 1)
        self.identity.revoke_grant(historic.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        with self.assertRaises(TaskError) as error:
            self.consumer.contributions(snapshot, self.reset, NOW)
        self.assertEqual(error.exception.code, "authorization_revoked")
        self.assertEqual(self.consumer.capture(self.reset, NOW)["reason"], "authorization_revoked")

    def test_rebinding_the_original_persona_invalidates_cross_reset_consumption(self):
        snapshot = self.consumer.capture(self.reset, NOW)
        route = self.personas.route(SCOPE)
        selector = next(selector for selector, _ in route.selectors() if selector.kind is SelectorKind.SESSION)
        self.personas.set_binding(PersonaBinding("original-session-switch", selector,
            SubjectRef(INSTALLATION, SubjectKind.BOT, "another-role"), 0, NOW, "test", "test"),
            expected_revision=0, observed_at=NOW)
        with self.assertRaises(TaskError) as error:
            self.consumer.contributions(snapshot, self.reset, NOW)
        self.assertEqual(error.exception.code, "relationship_source_scope")

    def test_revoked_original_source_cannot_be_restored_by_reset_or_admin_adoption(self):
        snapshot = self.consumer.capture(self.reset, NOW)
        self.messages.sources.revoke(self.memory.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError) as error:
            self.consumer.contributions(snapshot, self.reset, NOW)
        self.assertEqual(error.exception.code, "source_revoked")
        manager = RelationshipMemoryManagement(self.service)
        item = manager.list(operator=self.core, context=self.reset).unwrap()["items"][0]
        self.assertIsNone(item["interpretation"])
        self.assertEqual(item["actions"], ["retract"])

    def test_different_native_route_or_human_does_not_inherit_the_relationship(self):
        other = self.context_for(self.important,
            replace(SCOPE, native_scope_id="another-private-route", conversation_id="other", session_id="other"))
        self.assertEqual(self.consumer.capture(other, NOW)["references"], [])
        another_person = self.context_for(self.standard)
        self.grant(self.standard, another_person.scope, "relationship.memory.read")
        self.assertEqual(self.consumer.capture(another_person, NOW)["references"], [])
        group_scope = replace(self.reset.scope, kind=ScopeKind.GROUP)
        group = replace(self.reset, role_binding=replace(self.reset.role_binding, scope=group_scope),
                        audience=replace(self.reset.audience, scope=group_scope))
        self.assertEqual(self.consumer.capture(group, NOW)["reason"], "relationship_private_audience_required")


if __name__ == "__main__":
    unittest.main()
