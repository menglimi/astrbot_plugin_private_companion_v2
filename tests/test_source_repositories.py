from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.execution.models import digest
from companion_v2.foundation.refs import (
    AssetRef,
    AudienceRef,
    ScopeKind,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    VersionRef,
)
from companion_v2.identity_policy.directory import IdentityDirectory
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier, FailureCode
from companion_v2.sources.models import AssetRecord, EvidenceRecord, GovernanceState, SourceRecord
from companion_v2.sources.repositories import AssetRepository, EvidenceRepository, SourceRepository
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


def subject(subject_id: str = "subject-a") -> SubjectRef:
    return SubjectRef(
        installation_id=INSTALLATION_ID,
        kind=SubjectKind.HUMAN,
        subject_id=subject_id,
    )


def policy() -> IdentityDirectory:
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


class SourceRepositoryTests(unittest.TestCase):
    def test_current_source_inventory_rechecks_scope_audience_authorization_and_hash(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-source-inventory-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary) / "v2-data", installation_id=INSTALLATION_ID)
            sources = SourceRepository(runtime)
            directory = policy()
            resolved = directory.resolve_authenticated(principal(), observed_at=NOW).unwrap()

            def publish(source_id, owner, payload, *, source_scope=None, recipients=None, expires_at=None):
                source_scope = source_scope or scope()
                reference = SourceRef(source_id, owner, source_scope,
                    VersionRef(lineage_id=source_id + "-lineage", revision=1),
                    NOW - timedelta(minutes=1), expires_at)
                record = SourceRecord(reference,
                    AudienceRef(source_scope, recipients if recipients is not None else (subject(),)),
                    digest(payload), payload)
                sources.publish(record, observed_at=NOW).unwrap()

            publish("current", "proactive.news", '{"title":"current"}', expires_at=NOW + timedelta(minutes=5))
            publish("expired", "proactive.news", '{"title":"expired"}', expires_at=NOW - timedelta(seconds=1))
            publish("wrong-audience", "proactive.news", '{"title":"private"}',
                    recipients=(subject("subject-b"),))
            other_scope = ScopeRef(INSTALLATION_ID, "onebot", ScopeKind.PRIVATE, "private-b")
            publish("other-scope", "proactive.news", '{"title":"other"}', source_scope=other_scope)
            publish("other-owner", "conversation", '{"title":"other owner"}')

            records = sources.list_readable_current(scope(), owners=("proactive.news",),
                expected_recipients=(subject(),), resolved=resolved, capability=CAPABILITY,
                observed_at=NOW, authorizer=directory)
            self.assertEqual([record.reference.source_id for record in records], ["current"])
            runtime.close()

    def test_source_evidence_and_asset_are_readable_only_with_current_access(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-source-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary) / "v2-data", installation_id=INSTALLATION_ID)
            sources = SourceRepository(runtime)
            evidence = EvidenceRepository(runtime, sources)
            assets = AssetRepository(runtime)
            directory = policy()
            reference = source_reference()
            audience = AudienceRef(scope=scope(), recipients=(subject(),))
            source_record = SourceRecord(
                reference=reference,
                audience=audience,
                content_hash="source-hash-a",
                payload="fixture source",
            )
            evidence_record = EvidenceRecord(
                evidence_id="evidence-a",
                source=reference,
                version=VersionRef(lineage_id="evidence-lineage-a", revision=1),
                observed_at=NOW,
                content_hash="evidence-hash-a",
                payload="fixture evidence",
            )
            asset_reference = AssetRef(
                asset_id="asset-a",
                owner="world",
                scope=scope(),
                version=VersionRef(lineage_id="asset-lineage-a", revision=1),
                content_hash="asset-hash-a",
            )
            asset_record = AssetRecord(reference=asset_reference, audience=audience)
            resolved = directory.resolve_authenticated(principal(), observed_at=NOW).unwrap()

            self.assertTrue(sources.publish(source_record, observed_at=NOW).is_success)
            self.assertTrue(evidence.publish(evidence_record).is_success)
            self.assertTrue(assets.publish(asset_record, observed_at=NOW).is_success)
            self.assertEqual(
                sources.read(
                    reference,
                    resolved=resolved,
                    capability=CAPABILITY,
                    observed_at=NOW,
                    authorizer=directory,
                ).unwrap(),
                source_record,
            )
            self.assertEqual(
                evidence.read(
                    evidence_id="evidence-a",
                    version=evidence_record.version,
                    source=reference,
                    resolved=resolved,
                    capability=CAPABILITY,
                    observed_at=NOW,
                    authorizer=directory,
                ).unwrap(),
                evidence_record,
            )
            runtime.close()

            restarted_runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id=INSTALLATION_ID,
            )
            restarted_sources = SourceRepository(restarted_runtime)
            restarted_evidence = EvidenceRepository(restarted_runtime, restarted_sources)
            restarted_resolved = directory.resolve_authenticated(
                principal(), observed_at=NOW
            ).unwrap()
            self.assertEqual(
                restarted_sources.read(
                    reference,
                    resolved=restarted_resolved,
                    capability=CAPABILITY,
                    observed_at=NOW,
                    authorizer=directory,
                ).unwrap(),
                source_record,
            )
            self.assertEqual(
                restarted_evidence.read(
                    evidence_id="evidence-a",
                    version=evidence_record.version,
                    source=reference,
                    resolved=restarted_resolved,
                    capability=CAPABILITY,
                    observed_at=NOW,
                    authorizer=directory,
                ).unwrap(),
                evidence_record,
            )
            runtime = restarted_runtime
            assets = AssetRepository(runtime)
            self.assertEqual(
                assets.read(
                    asset_reference,
                    resolved=resolved,
                    capability=CAPABILITY,
                    observed_at=NOW,
                    authorizer=directory,
                ).unwrap(),
                asset_record,
            )
            self.assertEqual(
                assets.revoke(
                    asset_reference,
                    expected_governance_revision=1,
                    observed_at=NOW,
                ).unwrap().state,
                GovernanceState.REVOKED,
            )
            self.assertEqual(
                assets.read(
                    asset_reference,
                    resolved=resolved,
                    capability=CAPABILITY,
                    observed_at=NOW,
                    authorizer=directory,
                ).failure.code,
                "asset_revoked",
            )
            runtime.close()

    def test_revocation_rebinding_expiry_and_source_cas_do_not_become_empty_reads(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-source-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary) / "v2-data", installation_id=INSTALLATION_ID)
            sources = SourceRepository(runtime)
            directory = policy()
            reference = source_reference(expires_at=NOW + timedelta(minutes=5))
            record = SourceRecord(
                reference=reference,
                audience=AudienceRef(scope=scope(), recipients=(subject(),)),
                content_hash="source-hash-a",
                payload="fixture source",
            )
            sources.publish(record, observed_at=NOW).unwrap()
            resolved = directory.resolve_authenticated(principal(), observed_at=NOW).unwrap()

            governance_conflict = sources.revoke(
                reference,
                expected_governance_revision=2,
                observed_at=NOW,
            )
            revoked = sources.revoke(
                reference,
                expected_governance_revision=1,
                observed_at=NOW,
            )
            source_revoked = sources.read(
                reference,
                resolved=resolved,
                capability=CAPABILITY,
                observed_at=NOW,
                authorizer=directory,
            )

            self.assertEqual(governance_conflict.failure.code, "source_governance_conflict")
            self.assertEqual(revoked.unwrap().state, GovernanceState.REVOKED)
            self.assertEqual(source_revoked.failure.code, "source_revoked")

            expiring_reference = SourceRef(
                source_id="source-b",
                owner="conversation",
                scope=scope(),
                version=VersionRef(lineage_id="source-lineage-b", revision=1),
                issued_at=NOW,
                expires_at=NOW + timedelta(seconds=1),
            )
            sources.publish(
                SourceRecord(
                    reference=expiring_reference,
                    audience=AudienceRef(scope=scope(), recipients=(subject(),)),
                    content_hash="source-hash-b",
                    payload="fixture expired source",
                ),
                observed_at=NOW,
            ).unwrap()
            expired = sources.read(
                expiring_reference,
                resolved=resolved,
                capability=CAPABILITY,
                observed_at=NOW + timedelta(minutes=1),
                authorizer=directory,
            )
            self.assertEqual(expired.failure.code, "source_expired")

            fresh_reference = SourceRef(
                source_id="source-c",
                owner="conversation",
                scope=scope(),
                version=VersionRef(lineage_id="source-lineage-c", revision=1),
                issued_at=NOW,
            )
            sources.publish(
                SourceRecord(
                    reference=fresh_reference,
                    audience=AudienceRef(scope=scope(), recipients=(subject(),)),
                    content_hash="source-hash-c",
                    payload="fixture fresh source",
                ),
                observed_at=NOW,
            ).unwrap()

            rebound_directory = policy()
            rebound_directory.bind(
                binding_id="binding-b",
                principal=principal(),
                subject=subject("subject-b"),
                valid_from=NOW + timedelta(seconds=1),
            )
            rebound_directory.issue_grant(
                grant_id="grant-b",
                subject=subject("subject-b"),
                scope=scope(),
                capability=CAPABILITY,
                tier=AuthorizationTier.IMPORTANT,
                valid_from=NOW + timedelta(seconds=1),
            )
            stale_after_rebind = sources.read(
                fresh_reference,
                resolved=resolved,
                capability=CAPABILITY,
                observed_at=NOW + timedelta(minutes=1),
                authorizer=rebound_directory,
            )
            current_after_rebind = rebound_directory.resolve_authenticated(
                principal(), observed_at=NOW + timedelta(minutes=1)
            ).unwrap()
            rebound_audience = sources.read(
                fresh_reference,
                resolved=current_after_rebind,
                capability=CAPABILITY,
                observed_at=NOW + timedelta(minutes=1),
                authorizer=rebound_directory,
            )
            self.assertEqual(stale_after_rebind.failure.code, FailureCode.BINDING_REBOUND.value)
            self.assertEqual(rebound_audience.failure.code, "source_audience_denied")

            directory.revoke_grant("grant-a", revoked_at=NOW + timedelta(seconds=1))
            revoked_access = sources.read(
                fresh_reference,
                resolved=resolved,
                capability=CAPABILITY,
                observed_at=NOW + timedelta(minutes=1),
                authorizer=directory,
            )
            self.assertEqual(revoked_access.failure.code, FailureCode.AUTHORIZATION_REVOKED.value)
            runtime.close()
