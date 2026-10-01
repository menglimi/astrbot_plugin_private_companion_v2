from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.adapters.astrbot.inbound import AstrBotInboundAdapter
from companion_v2.agenda.models import AgendaTarget
from companion_v2.agenda.service import AgendaService
from companion_v2.capabilities import CapabilityRepository
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.service import ConfigurationService
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.refs import (
    AudienceRef, OperationRef, ReferenceValidationError, RoleOwnerRef, ScopeKind, ScopeRef,
    SourceRef, SubjectKind, SubjectRef, VersionRef,
)
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.identity_policy.personas import ConversationRoute, PersonaBinding, PersonaDirectory, RuntimeIdentity, SelectorKind
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.role_work.models import RoleActivity, RoleActivityState, RoleArtifact, RoleArtifactKind, RoleLifeLedger
from companion_v2.sharing.models import ShareMaterial
from companion_v2.sharing.planner import ShareCatalog, SharePlanner
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import AssetRepository, SourceRepository
from companion_v2.storage.repositories import OperationRepository
from companion_v2.storage.runtime import StorageRuntime
from tests import test_configuration as configuration_fixture
from tests import test_foreground_conversation as foreground_fixture
from tests.g6_support import descriptor
from tests.test_conversation_scope_and_role import RecordingModel


NOW = foreground_fixture.NOW
INSTALLATION = "multibot-installation"
ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "same-persona")
BASE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "same-native-window",
                "bot-a", "login-a", "conversation-a", "session-a")


@dataclass(frozen=True)
class HostEvent:
    scope: ScopeRef
    principal: AuthenticatedHostPrincipal
    subject: SubjectRef
    body: str
    native_id: str = "same-native-message"


class EventPort:
    def scope(self, event): return event.scope
    def event_id(self, event): return event.native_id
    def audience(self, event): return AudienceRef(event.scope, (event.subject,))
    def payload(self, event): return event.body
    def payload_hash(self, event): return hashlib.sha256(event.body.encode("utf-8")).hexdigest()
    def received_at(self, event): return NOW
    def authenticated_principal(self, event): return Outcome.success(event.principal)
    def conversation_route(self, event):
        if event.scope.kind is ScopeKind.PRIVATE:
            return ConversationRoute(event.scope, user=event.subject)
        return ConversationRoute(event.scope, group_id=event.scope.conversation_id,
                                 thread_parent_kind=ScopeKind.GROUP if event.scope.kind is ScopeKind.THREAD else None)


class MultiBotScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-multibot-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.identity = PersistentIdentityDirectory(self.runtime)
        self.sources = SourceRepository(self.runtime)
        self.policy = ObjectAccessPolicy(self.runtime)
        self.personas = PersonaDirectory(self.runtime)
        self.runtime_identity = RuntimeIdentity("ecosystem-a", "runtime-a", "astrbot", "same-host")
        self.counter = 0

    def participant(self, scope, *, shared_subject=None):
        self.counter += 1
        principal = AuthenticatedHostPrincipal(INSTALLATION, "same-host", scope.platform, "same-native-user",
                                               scope.bot_id, scope.account_id)
        existing = self.identity.resolve_authenticated(principal, observed_at=NOW)
        if existing.is_success:
            subject = existing.unwrap().subject
        else:
            subject = shared_subject or SubjectRef(INSTALLATION, SubjectKind.HUMAN, f"person-{self.counter}")
            self.identity.bind(binding_id=f"binding-{self.counter}", principal=principal, subject=subject,
                               valid_from=NOW, expected_revision=self.identity.revision)
        self.identity.issue_grant(grant_id=f"read-{self.counter}", subject=subject, scope=scope,
                                  capability="conversation.read", tier=AuthorizationTier.STANDARD,
                                  valid_from=NOW, expected_revision=self.identity.revision)
        route = (ConversationRoute(scope, user=subject) if scope.kind is ScopeKind.PRIVATE else
                 ConversationRoute(scope, group_id=scope.conversation_id,
                                   thread_parent_kind=ScopeKind.GROUP if scope.kind is ScopeKind.THREAD else None))
        if self.personas.route(scope) is None:
            self.personas.register_route(route, observed_at=NOW)
        if self.identity.role_binding(scope, observed_at=NOW) is None:
            self.identity.bind_role(scope=scope, role=ROLE, expected_revision=0, observed_at=NOW)
        actor = self.identity.resolve_authenticated(principal, observed_at=NOW).unwrap()
        self.policy.set_tier(subject, AuthorizationTier.IMPORTANT, observed_at=NOW, expected_revision=self.policy.revision)
        return actor

    def ingest(self, scope):
        actor = self.participant(scope)
        host_event = HostEvent(scope, actor.principal, actor.subject, f"来自 {scope.key} 的合成输入")
        adapter = AstrBotInboundAdapter(event_port=EventPort(), identity_port=EventPort(),
                                        identities=self.identity, personas=self.personas,
                                        runtime_identity=self.runtime_identity, sources=self.sources)
        return adapter.ingest(host_event, capability="conversation.read").unwrap(), actor

    def operation(self, scope, owner="agenda"):
        self.counter += 1
        identifier = f"operation-{self.counter}"
        return OperationRef(identifier, owner, scope, VersionRef(identifier, 1), identifier)

    def test_bot_account_conversation_and_session_each_isolate_same_native_message(self):
        variants = (BASE, replace(BASE, bot_id="bot-b"), replace(BASE, account_id="login-b"),
                    replace(BASE, conversation_id="conversation-b"), replace(BASE, session_id="session-b"))
        model = RecordingModel()
        pipeline = foreground_fixture.pipeline(self.runtime, self.sources, self.identity, model,
                                                foreground_fixture.ExternalEffectCounters(), role_bindings=self.identity, now=lambda: NOW)
        events = [self.ingest(scope)[0] for scope in variants]
        for event in events:
            result = pipeline.process(event, role_instruction="保持原角色", role_binding=self.identity.role_binding(event.scope)).unwrap()
            self.assertFalse(result.inbox_replayed)
            self.assertEqual(result.operation.scope, event.scope)
        self.assertEqual(len({event.source.source_id for event in events}), 5)
        self.assertEqual(len(OperationRepository(self.runtime).pending_outbox()), 5)
        self.assertEqual(len(model.requests), 5)
        for event in events:
            replay = pipeline.process(event, role_instruction="保持原角色", role_binding=self.identity.role_binding(event.scope)).unwrap()
            self.assertTrue(replay.inbox_replayed)
            self.assertTrue(replay.operation_replayed)

    def test_host_captured_persona_cannot_be_restamped_by_pipeline_caller(self):
        event, _ = self.ingest(BASE)
        model = RecordingModel()
        pipeline = foreground_fixture.pipeline(self.runtime, self.sources, self.identity, model,
                                                foreground_fixture.ExternalEffectCounters(),
                                                role_bindings=self.identity, now=lambda: NOW)
        wrong = replace(event.runtime_scope.persona, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "other-role"))
        result = pipeline.process(event, role_instruction="不应使用", role_binding=wrong)
        self.assertEqual(result.failure.code, "role_binding_input_mismatch")
        self.assertEqual(model.requests, [])
        pipeline.process(event, role_instruction="原角色可信提示").unwrap()
        with self.assertRaisesRegex(ReferenceValidationError, "cannot replace"):
            replace(model.requests[0], role_binding=wrong)

    def test_registered_persona_switch_and_switch_back_invalidates_host_event(self):
        event, _ = self.ingest(BASE)
        original = event.runtime_scope.persona
        self.identity.bind_role(scope=BASE, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "temporary"),
                                expected_revision=original.revision, observed_at=NOW)
        temporary = self.identity.resolve_role(BASE, observed_at=NOW).unwrap()
        self.identity.bind_role(scope=BASE, role=original.role, expected_revision=temporary.revision, observed_at=NOW)
        model = RecordingModel()
        pipeline = foreground_fixture.pipeline(self.runtime, self.sources, self.identity, model,
                                                foreground_fixture.ExternalEffectCounters(),
                                                role_bindings=self.identity, now=lambda: NOW)
        result = pipeline.process(event, role_instruction="过期的原角色提示")
        self.assertEqual(result.failure.code, "role_binding_changed")
        self.assertEqual(model.requests, [])

    def test_temporary_persona_expiring_during_generation_prevents_local_commit(self):
        self.participant(BASE)
        selector = next(selector for selector, _ in self.personas.route(BASE).selectors()
                        if selector.kind is SelectorKind.SESSION)
        self.personas.set_binding(PersonaBinding("temporary", selector,
            SubjectRef(INSTALLATION, SubjectKind.BOT, "temporary-persona"), 1, NOW, "fixture", "admin",
            effective_until=NOW + timedelta(seconds=1)), expected_revision=0, observed_at=NOW)
        event, _ = self.ingest(BASE)
        clock = DeterministicClock.at(NOW)
        model = RecordingModel(during=lambda: clock.advance(timedelta(seconds=1)))
        pipeline = foreground_fixture.pipeline(self.runtime, self.sources, self.identity, model,
                                                foreground_fixture.ExternalEffectCounters(),
                                                role_bindings=self.identity, now=clock.now)
        result = pipeline.process(event, role_instruction="临时角色提示")
        self.assertEqual(result.failure.code, "role_binding_changed")
        self.assertEqual(len(model.requests), 1)
        self.assertEqual(OperationRepository(self.runtime).pending_outbox(), ())

    def test_same_native_sender_has_separate_binding_per_bot_and_login(self):
        actors = [self.participant(scope) for scope in (BASE, replace(BASE, bot_id="bot-b"), replace(BASE, account_id="login-b"))]
        self.assertEqual(len({actor.subject for actor in actors}), 3)
        self.identity.revoke_binding(actors[0].binding_id, revoked_at=NOW, expected_revision=self.identity.revision)
        self.assertFalse(self.identity.resolve_authenticated(actors[0].principal, observed_at=NOW).is_success)
        for actor in actors[1:]:
            self.assertEqual(self.identity.resolve_authenticated(actor.principal, observed_at=NOW).unwrap().subject, actor.subject)

    def test_host_rejects_missing_or_mismatched_route_before_publishing(self):
        actor = self.participant(BASE)
        adapter = AstrBotInboundAdapter(event_port=EventPort(), identity_port=EventPort(), identities=self.identity,
                                        personas=self.personas, runtime_identity=self.runtime_identity,
                                        sources=self.sources)
        unresolved = ScopeRef(INSTALLATION, BASE.platform, BASE.kind, BASE.native_scope_id)
        for scope, code in ((unresolved, "scope_unresolved"), (replace(BASE, bot_id="other-bot"), "host_account_scope_mismatch")):
            result = adapter.ingest(HostEvent(scope, actor.principal, actor.subject, "不应保存"), capability="conversation.read")
            self.assertEqual(result.failure.code, code)
        self.assertEqual(self.runtime.read_all("SELECT * FROM sources", ()), ())
        with self.assertRaises(ReferenceValidationError):
            replace(BASE, session_id=None)

    def test_cross_bot_source_read_and_binding_changes_do_not_leak(self):
        first, actor_a = self.ingest(BASE)
        second, actor_b = self.ingest(replace(BASE, bot_id="bot-b"))
        denied = self.sources.read(first.source, resolved=actor_b, capability="conversation.read", observed_at=NOW, authorizer=self.identity)
        self.assertFalse(denied.is_success)
        self.identity.bind_role(scope=BASE, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "other-persona"), expected_revision=1)
        self.assertEqual(self.identity.role_binding(second.scope).role, ROLE)
        self.assertEqual(self.identity.role_binding(second.scope).revision, 1)
        self.assertTrue(self.sources.read(second.source, resolved=actor_b, capability="conversation.read", observed_at=NOW, authorizer=self.identity).is_success)

    def test_same_role_configuration_is_separate_per_bot_and_restores_after_restart(self):
        actor_a = self.participant(BASE)
        actor_b = self.participant(replace(BASE, bot_id="bot-b"))
        service = ConfigurationService(self.runtime, configuration_fixture.registry())
        windows = (ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, BASE),
                   ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, replace(BASE, bot_id="bot-b")))
        targets = tuple(ConfigTarget(INSTALLATION, ConfigLayer.ROLE, ROLE, bot_id=target.bot_id) for target in windows)
        for index, (actor, target, window) in enumerate(zip((actor_a, actor_b), targets, windows)):
            for item_index, item in enumerate((target, window)):
                for capability in ("configuration.read", "configuration.write"):
                    self.identity.issue_grant(grant_id=f"config-{index}-{item_index}-{capability}", subject=actor.subject,
                                              scope=item.authorization_scope, capability=capability, tier=AuthorizationTier.STANDARD,
                                              valid_from=NOW, expected_revision=self.identity.revision)
            snapshot = service.read(actor, target=target, group_id="output", observed_at=NOW).unwrap()
            service.patch(actor, target=target, group_id="output", operation=self.operation(target.authorization_scope, "configuration"),
                          expected_edit_token=snapshot.edit_token, changes={"output.prompt": f"bot-{index}-only"},
                          observed_at=NOW).unwrap()
            value = service.read(actor, target=window, group_id="output", observed_at=NOW).unwrap()
            self.assertEqual(value.fields["output.prompt"].source, target)
        self.assertNotEqual(targets[0].key, targets[1].key)
        self.runtime.close()
        reopened = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(reopened.close)
        service = ConfigurationService(reopened, configuration_fixture.registry())
        for index, (actor, window) in enumerate(zip((actor_a, actor_b), windows)):
            self.assertEqual(service.read(actor, target=window, group_id="output", observed_at=NOW).unwrap().values["output.prompt"], f"bot-{index}-only")

    def test_memos_and_original_receipts_preserve_full_route_on_reopen(self):
        service = AgendaService(self.runtime)
        cases = []
        for index, scope in enumerate((BASE, replace(BASE, bot_id="bot-b"))):
            actor = self.participant(scope)
            target = AgendaTarget(scope, ROLE, actor.subject)
            receipt = service.create_memo(actor, target=target, memo_id=f"memo-{index}", title=f"bot {index}", body="私有正文",
                                           operation=self.operation(scope), expected_role_revision=1, observed_at=NOW).unwrap()
            cases.append((actor, target, receipt))
        self.runtime.close()
        reopened = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(reopened.close)
        service = AgendaService(reopened)
        for actor, target, receipt in cases:
            memos = service.list_memos(actor, target=target, observed_at=NOW).unwrap()
            self.assertEqual(len(memos), 1)
            self.assertEqual(memos[0].target.scope, target.scope)
            self.assertTrue(service.receipt(actor, target=target, operation_id=receipt.operation_id, observed_at=NOW).is_success)
        actor, _, _ = cases[0]
        self.assertEqual(service.read_memo(actor, target=cases[1][1], memo_id="memo-1", observed_at=NOW).failure.code, "agenda_object_not_found")

    def test_capability_role_enablement_and_preferences_do_not_cross_bots(self):
        capabilities = CapabilityRepository(self.runtime)
        package = descriptor()
        capabilities.register_descriptor(package, registered_at=NOW).unwrap()
        capabilities.acquire(extension_id=package.extension_id, package_id=package.package_id, package_version=package.package_version,
                             expected_revision=0, observed_at=NOW).unwrap()
        for index, scope in enumerate((BASE, replace(BASE, bot_id="bot-b"))):
            capabilities.set_role_enabled(extension_id=package.extension_id, role=ROLE, bot_id=scope.bot_id, enabled=index == 0,
                                          expected_revision=0, observed_at=NOW).unwrap()
            capabilities.set_settings(extension_id=package.extension_id, scope=scope, proactive_enabled=index == 0, thought_weight=index + 1,
                                      expected_revision=0, observed_at=NOW).unwrap()
            projection = capabilities.projection(extension_id=package.extension_id, role=ROLE, scope=scope).unwrap()
            self.assertEqual(projection.role_selection.bot_id, scope.bot_id)
            self.assertEqual(projection.role_selection.enabled, index == 0)
            self.assertEqual(projection.settings.thought_weight, index + 1)
        self.assertFalse(capabilities.require_role_enabled(extension_id=package.extension_id, role=ROLE, bot_id="bot-b").is_success)

    def test_role_album_uses_stable_owner_and_sharing_preserves_the_creator(self):
        ledger = RoleLifeLedger()
        variants = ((BASE, "persona-a"), (BASE, "persona-b"), (replace(BASE, bot_id="bot-b"), "persona-a"),
                    (replace(BASE, session_id="session-b"), "persona-a"))
        artifacts = []
        for index, (scope, persona) in enumerate(variants):
            ledger.add_activity(RoleActivity(f"activity-{index}", persona, scope, NOW, RoleActivityState.COMPLETED))
            source = SourceRef(f"artifact-source-{index}", "role.life", scope, VersionRef(f"artifact-source-{index}", 1), NOW)
            artifacts.append(ledger.add_artifact(RoleArtifact(f"artifact-{index}", f"activity-{index}", RoleArtifactKind.TEXT, source, NOW)))
        owner = RoleOwnerRef(INSTALLATION, "bot-a", "persona-a")
        self.assertEqual(ledger.artifacts_for_scope(BASE, owner=owner), (artifacts[0],))
        self.assertEqual(ledger.artifacts_for_role(owner), (artifacts[0], artifacts[3]))
        with self.assertRaises(KeyError):
            ledger.artifact(artifacts[1].artifact_id, owner=owner)
        with self.assertRaises(ReferenceValidationError):
            ledger.add_artifact(replace(artifacts[0], artifact_id="forged", owner=artifacts[1].owner))
        material = ShareMaterial.from_role_artifact(artifacts[0])
        actor = self.participant(BASE)
        self.sources.publish(SourceRecord(material.source, AudienceRef(BASE, (actor.subject,)), "hash", "角色 A 的作品"), observed_at=NOW).unwrap()
        planner = SharePlanner(sources=self.sources, assets=AssetRepository(self.runtime), catalog=ShareCatalog())
        parameters = dict(resolved=actor, capability="conversation.read", observed_at=NOW, authorizer=self.identity)
        denied = planner.prepare(material, role_owner=artifacts[1].owner, **parameters)
        self.assertEqual(denied.failure.code, "share_role_owner_mismatch")
        candidate = planner.prepare(material, role_owner=owner, **parameters).unwrap()
        self.assertEqual(planner.follow_up_material(candidate.candidate_id, role_owner=artifacts[1].owner, **parameters).failure.code,
                         "share_role_owner_mismatch")


if __name__ == "__main__":
    unittest.main()
