from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.conversation.foreground import (
    ClaimKind,
    ContextContribution,
    ContributionState,
    DeterministicLocalModel,
    DraftClaim,
    EvidencePromptCompiler,
    ForegroundContextAssembler,
    ForegroundConversationPipeline,
    ForegroundLeaseRegistry,
    GroundedDraftReviewer,
    LeaseState,
    ModelDraft,
)
from companion_v2.conversation.models import ExternalEffectCounters, InboundConversationEvent
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.refs import (
    AudienceRef,
    ScopeKind,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    VersionRef,
)
from companion_v2.identity_policy.directory import IdentityDirectory
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier, RoleBinding
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.repositories import InboxRepository, OperationRepository
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
INSTALLATION_ID = "installation-alpha"
CAPABILITY = "conversation.read"


def scope() -> ScopeRef:
    return ScopeRef(
        installation_id=INSTALLATION_ID,
        platform="onebot",
        kind=ScopeKind.PRIVATE,
        native_scope_id="private-a",
    )


def subject() -> SubjectRef:
    return SubjectRef(
        installation_id=INSTALLATION_ID,
        kind=SubjectKind.HUMAN,
        subject_id="subject-a",
    )


def role_binding() -> RoleBinding:
    return RoleBinding(scope(), SubjectRef(INSTALLATION_ID, SubjectKind.BOT, "role-a"), 1)


def principal() -> AuthenticatedHostPrincipal:
    return AuthenticatedHostPrincipal(
        installation_id=INSTALLATION_ID,
        host_id="astrbot-fixture-host",
        platform="onebot",
        native_account_id="account-a",
    )


def identity_directory() -> IdentityDirectory:
    directory = IdentityDirectory()
    directory.bind(
        binding_id="binding-a",
        principal=principal(),
        subject=subject(),
        valid_from=NOW - timedelta(minutes=1),
    )
    directory.issue_grant(
        grant_id="grant-a",
        subject=subject(),
        scope=scope(),
        capability=CAPABILITY,
        tier=AuthorizationTier.IMPORTANT,
        valid_from=NOW - timedelta(minutes=1),
    )
    return directory


def reference(source_id: str = "source-a") -> SourceRef:
    return SourceRef(
        source_id=source_id,
        owner="conversation",
        scope=scope(),
        version=VersionRef(lineage_id=f"{source_id}-lineage", revision=1),
        issued_at=NOW,
    )


def event(source: SourceRef) -> InboundConversationEvent:
    return InboundConversationEvent(
        event_id="event-a",
        principal=principal(),
        scope=scope(),
        source=source,
        capability=CAPABILITY,
        input_hash="event-input-hash-a",
        received_at=NOW,
    )


def publish(sources: SourceRepository, source: SourceRef) -> None:
    sources.publish(
        SourceRecord(
            reference=source,
            audience=AudienceRef(scope=scope(), recipients=(subject(),)),
            content_hash=f"{source.source_id}-hash",
            payload="synthetic source",
        ),
        observed_at=NOW,
    ).unwrap()


def pipeline(
    runtime: StorageRuntime,
    sources: SourceRepository,
    directory: IdentityDirectory,
    model: object,
    effects: ExternalEffectCounters,
    leases: ForegroundLeaseRegistry | None = None,
    *, role_bindings=None, now=None,
) -> ForegroundConversationPipeline:
    if role_bindings is None:
        role_bindings = PersistentIdentityDirectory(runtime)
        if role_bindings.role_binding(scope()) is None:
            role_bindings.bind_role(scope=scope(), role=role_binding().role, expected_revision=0)
    return ForegroundConversationPipeline(
        identities=directory,
        role_bindings=role_bindings,
        now=now or DeterministicClock.at(NOW).now,
        sources=sources,
        inbox=InboxRepository(runtime),
        operations=OperationRepository(runtime),
        leases=leases or ForegroundLeaseRegistry(),
        assembler=ForegroundContextAssembler(),
        compiler=EvidencePromptCompiler(),
        model=model,
        reviewer=GroundedDraftReviewer(),
        external_effects=effects,
    )


class UnsupportedFirstModel:
    def __init__(self, unsupported: SourceRef) -> None:
        self._unsupported = unsupported
        self.generate_calls = 0
        self.revise_calls = 0

    def generate(self, request: object) -> ModelDraft:
        del request
        self.generate_calls += 1
        return ModelDraft(
            text="I will present an unsupported user fact.",
            claims=(
                DraftClaim(
                    claim_id="unsupported-user-fact",
                    kind=ClaimKind.OBSERVED,
                    statement="A made-up current user action.",
                    evidence=self._unsupported,
                ),
            ),
        )

    def revise(self, request: object, draft: ModelDraft, review: object) -> ModelDraft:
        del request, draft, review
        self.revise_calls += 1
        return ModelDraft(
            text="I can ask instead of treating an unsupported detail as observed.",
            claims=(
                DraftClaim(
                    claim_id="ask-instead",
                    kind=ClaimKind.QUESTION,
                    statement="Ask about the user's situation.",
                ),
            ),
        )


class RevokingModel:
    def __init__(self, sources: SourceRepository, source: SourceRef) -> None:
        self._sources = sources
        self._source = source

    def generate(self, request: object) -> ModelDraft:
        del request
        self._sources.revoke(
            self._source,
            expected_governance_revision=1,
            observed_at=NOW,
        ).unwrap()
        return ModelDraft(
            text="A draft with a once-valid evidence reference.",
            claims=(
                DraftClaim(
                    claim_id="primary",
                    kind=ClaimKind.OBSERVED,
                    statement="Use the source that was present when generation began.",
                    evidence=self._source,
                ),
            ),
        )

    def revise(self, request: object, draft: ModelDraft, review: object) -> ModelDraft:
        del request, draft, review
        raise AssertionError("the first draft is structurally grounded")


class ForegroundConversationTests(unittest.TestCase):
    def test_ready_context_is_sealed_while_deferred_work_stays_off_the_foreground_path(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-g4-") as temporary:
            runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id=INSTALLATION_ID,
            )
            sources = SourceRepository(runtime)
            source = reference()
            publish(sources, source)
            directory = identity_directory()
            effects = ExternalEffectCounters()
            model = DeterministicLocalModel()
            foreground = pipeline(runtime, sources, directory, model, effects)

            result = foreground.process(
                event(source),
                role_instruction="Stay in character and respond naturally.",
                role_binding=role_binding(),
                contributions=(
                    ContextContribution(
                        contribution_id="relationship-ready",
                        owner="role",
                        purpose="relationship tone",
                        state=ContributionState.READY,
                        payload="synthetic relation projection",
                    ),
                    ContextContribution(
                        contribution_id="tts-deferred",
                        owner="voice",
                        purpose="voice enhancement",
                        state=ContributionState.DEFERRED,
                    ),
                ),
            ).unwrap()
            replay = foreground.process(
                event(source),
                role_instruction="Stay in character and respond naturally.",
                role_binding=role_binding(),
            ).unwrap()

            self.assertEqual(len(result.trace.deferred_work), 1)
            self.assertEqual(result.trace.deferred_work[0].owner, "voice")
            self.assertFalse(result.operation_replayed)
            self.assertTrue(replay.inbox_replayed)
            self.assertTrue(replay.operation_replayed)
            self.assertEqual(model.generate_calls, 2)
            self.assertTrue(effects.all_zero())
            self.assertEqual(len(OperationRepository(runtime).pending_outbox()), 1)
            runtime.close()

    def test_unsupported_observed_claim_is_revised_to_a_question_without_keyword_filtering(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-g4-") as temporary:
            runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id=INSTALLATION_ID,
            )
            sources = SourceRepository(runtime)
            source = reference()
            publish(sources, source)
            unsupported = reference("unsealed-source")
            model = UnsupportedFirstModel(unsupported)
            effects = ExternalEffectCounters()
            foreground = pipeline(runtime, sources, identity_directory(), model, effects)

            result = foreground.process(
                event(source),
                role_instruction="Stay in character and respond naturally.",
                role_binding=role_binding(),
            ).unwrap()

            self.assertEqual(model.generate_calls, 1)
            self.assertEqual(model.revise_calls, 1)
            self.assertEqual(result.draft.claims[0].kind, ClaimKind.QUESTION)
            self.assertTrue(effects.all_zero())
            runtime.close()

    def test_source_revoked_during_generation_blocks_local_outbox_commit(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-g4-") as temporary:
            runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id=INSTALLATION_ID,
            )
            sources = SourceRepository(runtime)
            source = reference()
            publish(sources, source)
            effects = ExternalEffectCounters()
            foreground = pipeline(
                runtime,
                sources,
                identity_directory(),
                RevokingModel(sources, source),
                effects,
            )

            result = foreground.process(
                event(source),
                role_instruction="Stay in character and respond naturally.",
                role_binding=role_binding(),
            )

            self.assertEqual(result.failure.code, "source_revoked")
            self.assertEqual(len(OperationRepository(runtime).pending_outbox()), 0)
            self.assertTrue(effects.all_zero())
            runtime.close()

    def test_cancelled_lease_cannot_be_reused_for_submission(self) -> None:
        registry = ForegroundLeaseRegistry()
        lease = registry.issue(event(reference()))
        cancelled = registry.cancel(lease)
        status = registry.verify_active(lease)

        self.assertEqual(cancelled.state, LeaseState.CANCELLED)
        self.assertEqual(status.failure.code, "foreground_lease_stale")
