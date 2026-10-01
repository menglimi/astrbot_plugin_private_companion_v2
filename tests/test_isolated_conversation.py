from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.conversation.kernel import IsolatedConversationKernel
from companion_v2.conversation.models import (
    DeterministicFakeRenderer,
    ExternalEffectCounters,
    InboundConversationEvent,
)
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
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
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


def principal() -> AuthenticatedHostPrincipal:
    return AuthenticatedHostPrincipal(
        installation_id=INSTALLATION_ID,
        host_id="astrbot-fixture-host",
        platform="onebot",
        native_account_id="account-a",
    )


def subject() -> SubjectRef:
    return SubjectRef(
        installation_id=INSTALLATION_ID,
        kind=SubjectKind.HUMAN,
        subject_id="subject-a",
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


def source_reference(*, expires_at: datetime | None = None) -> SourceRef:
    return SourceRef(
        source_id="source-a",
        owner="conversation",
        scope=scope(),
        version=VersionRef(lineage_id="source-lineage-a", revision=1),
        issued_at=NOW,
        expires_at=expires_at,
    )


def event(reference: SourceRef, *, received_at: datetime = NOW) -> InboundConversationEvent:
    return InboundConversationEvent(
        event_id="event-a",
        principal=principal(),
        scope=scope(),
        source=reference,
        capability=CAPABILITY,
        input_hash="event-input-hash-a",
        received_at=received_at,
    )


def publish_source(sources: SourceRepository, reference: SourceRef) -> None:
    sources.publish(
        SourceRecord(
            reference=reference,
            audience=AudienceRef(scope=scope(), recipients=(subject(),)),
            content_hash="source-hash-a",
            payload="synthetic source",
        ),
        observed_at=NOW,
    ).unwrap()


class IsolatedConversationKernelTests(unittest.TestCase):
    def test_local_loop_creates_one_outbox_plan_without_external_effects(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-g3-") as temporary:
            runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id=INSTALLATION_ID,
            )
            sources = SourceRepository(runtime)
            reference = source_reference()
            publish_source(sources, reference)
            renderer = DeterministicFakeRenderer()
            effects = ExternalEffectCounters()
            operations = OperationRepository(runtime)
            kernel = IsolatedConversationKernel(
                identities=identity_directory(),
                sources=sources,
                inbox=InboxRepository(runtime),
                operations=operations,
                renderer=renderer,
                external_effects=effects,
            )

            result = kernel.process(event(reference)).unwrap()

            self.assertFalse(result.inbox_replayed)
            self.assertFalse(result.operation_receipt.replayed)
            self.assertEqual(result.expression.text, "isolated-ack:acknowledge_available_source:source-a:1")
            self.assertEqual(renderer.render_calls, 1)
            self.assertEqual(len(operations.pending_outbox()), 1)
            self.assertTrue(effects.all_zero())
            runtime.close()

    def test_replay_after_restart_preserves_the_operation_and_never_sends(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-g3-") as temporary:
            root = Path(temporary) / "v2-data"
            runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            sources = SourceRepository(runtime)
            reference = source_reference()
            publish_source(sources, reference)
            identities = identity_directory()
            first_renderer = DeterministicFakeRenderer()
            first_effects = ExternalEffectCounters()
            first_kernel = IsolatedConversationKernel(
                identities=identities,
                sources=sources,
                inbox=InboxRepository(runtime),
                operations=OperationRepository(runtime),
                renderer=first_renderer,
                external_effects=first_effects,
            )
            first = first_kernel.process(event(reference)).unwrap()
            snapshot = identities.snapshot()
            runtime.close()

            restarted_runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            restarted_renderer = DeterministicFakeRenderer()
            restarted_effects = ExternalEffectCounters()
            restarted_operations = OperationRepository(restarted_runtime)
            restarted_kernel = IsolatedConversationKernel(
                identities=IdentityDirectory.from_snapshot(snapshot),
                sources=SourceRepository(restarted_runtime),
                inbox=InboxRepository(restarted_runtime),
                operations=restarted_operations,
                renderer=restarted_renderer,
                external_effects=restarted_effects,
            )
            replay = restarted_kernel.process(event(reference)).unwrap()

            self.assertTrue(replay.inbox_replayed)
            self.assertTrue(replay.operation_receipt.replayed)
            self.assertEqual(replay.expression, first.expression)
            self.assertEqual(len(restarted_operations.pending_outbox()), 1)
            self.assertTrue(first_effects.all_zero())
            self.assertTrue(restarted_effects.all_zero())
            restarted_runtime.close()

    def test_cancellation_and_expired_source_do_not_make_an_outbox(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-g3-") as temporary:
            runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id=INSTALLATION_ID,
            )
            sources = SourceRepository(runtime)
            valid_reference = source_reference()
            expired_reference = SourceRef(
                source_id="source-expired",
                owner="conversation",
                scope=scope(),
                version=VersionRef(lineage_id="source-lineage-expired", revision=1),
                issued_at=NOW,
                expires_at=NOW + timedelta(seconds=1),
            )
            publish_source(sources, valid_reference)
            publish_source(sources, expired_reference)
            effects = ExternalEffectCounters()
            operations = OperationRepository(runtime)
            kernel = IsolatedConversationKernel(
                identities=identity_directory(),
                sources=sources,
                inbox=InboxRepository(runtime),
                operations=operations,
                renderer=DeterministicFakeRenderer(),
                external_effects=effects,
            )

            cancelled = kernel.process(event(valid_reference), cancelled=True)
            expired = kernel.process(
                event(expired_reference, received_at=NOW + timedelta(minutes=1))
            )

            self.assertEqual(cancelled.failure.code, "cancelled")
            self.assertEqual(expired.failure.code, "source_expired")
            self.assertEqual(len(operations.pending_outbox()), 0)
            self.assertTrue(effects.all_zero())
            runtime.close()
