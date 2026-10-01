from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.conversation.foreground import (
    ContextContribution, ContributionState, ForegroundLeaseRegistry, ForegroundStage, ModelDraft,
)
from companion_v2.conversation.kernel import IsolatedConversationKernel
from companion_v2.conversation.models import DeterministicFakeRenderer, ExternalEffectCounters, InboundConversationEvent
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.refs import AudienceRef, ScopeKind, SourceRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.repositories import InboxRepository, OperationRepository
from companion_v2.storage.runtime import StorageRuntime
from tests import test_foreground_conversation as fixture


class RecordingModel:
    def __init__(self, during=None):
        self.requests = []
        self.during = during

    def generate(self, request):
        self.requests.append(request)
        if self.during is not None:
            self.during()
        return ModelDraft("沿原角色自然回应。", ())

    def revise(self, request, draft, review):
        raise AssertionError("these fixtures need no semantic revision")


class ConversationScopeAndRoleTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-scope-role-")
        self.addCleanup(temporary.cleanup)
        self.runtime = StorageRuntime.open(data_root=Path(temporary.name) / "data", installation_id=fixture.INSTALLATION_ID)
        self.addCleanup(self.runtime.close)
        self.sources = SourceRepository(self.runtime)
        self.identity = PersistentIdentityDirectory(self.runtime)
        self.clock = DeterministicClock.at(fixture.NOW)
        self.leases = ForegroundLeaseRegistry()
        self.effects = ExternalEffectCounters()
        self.counter = 0

    def inbound(self, *, scope=None, event_id="same-native-event", expires_at=None, recipients=None):
        scope = scope or fixture.scope()
        self.counter += 1
        sender = replace(fixture.principal(), platform=scope.platform)
        if not self.identity.resolve_authenticated(sender, observed_at=self.clock.now()).is_success:
            self.identity.bind(binding_id=f"binding-{self.counter}", principal=sender, subject=fixture.subject(),
                               valid_from=fixture.NOW, expected_revision=self.identity.revision)
        self.identity.issue_grant(grant_id=f"grant-{self.counter}", subject=fixture.subject(), scope=scope,
                                  capability=fixture.CAPABILITY, tier=AuthorizationTier.IMPORTANT,
                                  valid_from=fixture.NOW, expected_revision=self.identity.revision)
        if self.identity.role_binding(scope) is None:
            self.identity.bind_role(scope=scope, role=fixture.role_binding().role, expected_revision=0)
        source = SourceRef(f"source-{self.counter}", "conversation", scope, VersionRef(f"source-{self.counter}", 1),
                           fixture.NOW, expires_at)
        payload_hash = f"hash-{self.counter}"
        self.sources.publish(SourceRecord(source, AudienceRef(scope, recipients or (fixture.subject(),)), payload_hash, "合成输入"),
                             observed_at=fixture.NOW).unwrap()
        return InboundConversationEvent(event_id, sender, scope, source, fixture.CAPABILITY, payload_hash, fixture.NOW)

    def foreground(self, model):
        return fixture.pipeline(self.runtime, self.sources, self.identity, model, self.effects, self.leases,
                                role_bindings=self.identity, now=self.clock.now)

    def process(self, pipeline, event, **kwargs):
        return pipeline.process(event, role_instruction="当前角色的可信指令",
                                role_binding=self.identity.role_binding(event.scope), **kwargs)

    def rebind(self, scope, role_id):
        return self.identity.bind_role(scope=scope, role=SubjectRef(fixture.INSTALLATION_ID, SubjectKind.BOT, role_id),
                                       expected_revision=self.identity.role_binding(scope).revision)

    def test_equal_native_event_ids_across_windows_kinds_and_platforms_are_independent(self):
        window = fixture.scope()
        windows = (window, replace(window, native_scope_id="private-b"), replace(window, kind=ScopeKind.GROUP),
                   replace(window, platform="other-platform"))
        model = RecordingModel()
        pipeline = self.foreground(model)
        results = [self.process(pipeline, self.inbound(scope=scope)).unwrap() for scope in windows]
        self.assertEqual(len({result.operation.operation_id for result in results}), 4)
        self.assertTrue(all(not result.inbox_replayed and not result.operation_replayed for result in results))
        self.assertEqual(len(OperationRepository(self.runtime).pending_outbox()), 4)
        self.assertEqual(len(model.requests), 4)
        self.assertTrue(self.effects.all_zero())

    def test_cancelling_private_lease_does_not_cancel_same_number_group_event(self):
        private = self.inbound()
        group = self.inbound(scope=replace(private.scope, kind=ScopeKind.GROUP))
        first, second = self.leases.issue(private), self.leases.issue(group)
        self.assertEqual(second.source, group.source)
        self.assertNotEqual(first.lease_id, second.lease_id)
        self.leases.cancel(first)
        self.assertTrue(self.leases.verify_active(second).is_success)

    def test_g3_scoped_inbox_recovers_each_window_without_false_duplicate(self):
        def kernel():
            return IsolatedConversationKernel(identities=self.identity, sources=self.sources, inbox=InboxRepository(self.runtime),
                                               operations=OperationRepository(self.runtime), renderer=DeterministicFakeRenderer(),
                                               external_effects=self.effects)
        inputs = (self.inbound(), self.inbound(scope=replace(fixture.scope(), native_scope_id="private-b")))
        for event in inputs:
            result = kernel().process(event).unwrap()
            self.assertFalse(result.inbox_replayed)
        for event in inputs:
            result = kernel().process(event).unwrap()
            self.assertTrue(result.inbox_replayed)
            self.assertTrue(result.operation_receipt.replayed)
        self.assertEqual(len(OperationRepository(self.runtime).pending_outbox()), 2)

    def test_stale_role_instruction_is_rejected_before_model_or_inbox(self):
        event = self.inbound()
        original = self.identity.role_binding(event.scope)
        self.rebind(event.scope, "role-b")
        model = RecordingModel()
        result = self.foreground(model).process(event, role_instruction="旧 A 的指令", role_binding=original)
        self.assertEqual(result.failure.code, "role_binding_changed")
        self.assertEqual(model.requests, [])
        self.assertEqual(self.runtime.read_all("SELECT * FROM inbox", ()), ())

    def test_role_switch_and_switch_back_during_generation_invalidate_original_turn(self):
        for switch_back in (False, True):
            with self.subTest(switch_back=switch_back):
                event = self.inbound(event_id=f"role-switch-{switch_back}")
                original = self.identity.role_binding(event.scope)

                def switch():
                    self.rebind(event.scope, "temporary-role")
                    if switch_back:
                        self.rebind(event.scope, original.role.subject_id)

                model = RecordingModel(switch)
                result = self.foreground(model).process(event, role_instruction="原角色指令", role_binding=original)
                self.assertEqual(result.failure.code, "role_binding_changed")
                self.assertEqual(model.requests[0].role_binding, original)
        self.assertEqual(OperationRepository(self.runtime).pending_outbox(), ())

    def test_other_window_role_change_does_not_cancel_current_reply(self):
        event = self.inbound()
        other = self.inbound(scope=replace(event.scope, native_scope_id="other-window"))
        model = RecordingModel(lambda: self.rebind(other.scope, "role-b"))
        self.assertTrue(self.process(self.foreground(model), event).is_success)

    def test_expiry_during_generation_uses_current_clock_and_prevents_commit(self):
        event = self.inbound(expires_at=fixture.NOW + timedelta(seconds=1))
        model = RecordingModel(lambda: self.clock.advance(timedelta(seconds=2)))
        result = self.process(self.foreground(model), event)
        self.assertEqual(result.failure.code, "source_expired")
        self.assertEqual(OperationRepository(self.runtime).pending_outbox(), ())

    def test_forbidden_contribution_never_enters_model_input(self):
        event = self.inbound()
        reference = replace(event.source, source_id="someone-elses-source", version=VersionRef("someone-elses-source", 1))
        other = SubjectRef(fixture.INSTALLATION_ID, SubjectKind.HUMAN, "other-person")
        self.sources.publish(SourceRecord(reference, AudienceRef(event.scope, (other,)), "private-hash", "别人的私密资料"),
                             observed_at=fixture.NOW).unwrap()
        contribution = ContextContribution("private", "memory", "context", ContributionState.READY,
                                           payload="别人的私密资料", source=reference)
        model = RecordingModel()
        result = self.process(self.foreground(model), event, contributions=(contribution,))
        self.assertFalse(result.is_success)
        self.assertEqual(model.requests, [])
        self.assertEqual(OperationRepository(self.runtime).pending_outbox(), ())

    def test_trace_records_real_stage_times_instead_of_repeating_arrival_time(self):
        event = self.inbound()
        model = RecordingModel(lambda: self.clock.advance(timedelta(seconds=3)))
        result = self.process(self.foreground(model), event).unwrap()
        times = {step.stage: step.at for step in result.trace.steps}
        self.assertEqual(times[ForegroundStage.GENERATION_STARTED], fixture.NOW)
        self.assertEqual(times[ForegroundStage.FIRST_ELIGIBLE_UNIT] - times[ForegroundStage.GENERATION_STARTED], timedelta(seconds=3))
        self.assertEqual(times[ForegroundStage.LOCAL_OUTBOX_COMMITTED], self.clock.now())

    def test_sender_private_material_cannot_be_used_for_other_group_recipients(self):
        private = self.inbound()
        bystander = SubjectRef(fixture.INSTALLATION_ID, SubjectKind.HUMAN, "group-bystander")
        group = self.inbound(scope=replace(private.scope, kind=ScopeKind.GROUP), recipients=(fixture.subject(), bystander))
        contribution = ContextContribution("private", "memory", "context", ContributionState.READY,
                                           payload="调用者本人能读的私密资料", source=private.source)
        model = RecordingModel()
        result = self.process(self.foreground(model), group, contributions=(contribution,))
        self.assertEqual(result.failure.code, "source_audience_mismatch")
        self.assertEqual(model.requests, [])
        self.assertEqual(OperationRepository(self.runtime).pending_outbox(), ())

    def test_changed_role_cannot_reinterpret_original_committed_operation(self):
        event = self.inbound()
        self.process(self.foreground(RecordingModel()), event).unwrap()
        self.rebind(event.scope, "role-b")
        result = self.process(self.foreground(RecordingModel()), event)
        self.assertEqual(result.failure.code, "idempotency_key_conflict")
        self.assertEqual(len(OperationRepository(self.runtime).pending_outbox()), 1)


if __name__ == "__main__":
    unittest.main()
