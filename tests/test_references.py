from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from companion_v2.foundation.refs import (
    AssetRef,
    AttemptRef,
    AudienceRef,
    OperationRef,
    PartRef,
    ReferenceValidationError,
    ScopeKind,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    TaskRef,
    VersionRef,
)


NOW = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)


class ReferenceContractTests(unittest.TestCase):
    def test_versioned_references_share_an_exact_scope_without_paths(self) -> None:
        scope = ScopeRef(
            installation_id="installation-alpha",
            platform="onebot",
            kind=ScopeKind.PRIVATE,
            native_scope_id="private-a",
        )
        version = VersionRef(lineage_id="source-lineage-a", revision=3)
        source = SourceRef(
            source_id="source-a",
            owner="conversation",
            scope=scope,
            version=version,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )
        asset = AssetRef(
            asset_id="asset-a",
            owner="world",
            scope=scope,
            version=VersionRef(lineage_id="asset-lineage-a", revision=1),
            content_hash="sha256-fixture",
        )
        operation = OperationRef(
            operation_id="operation-a",
            owner="delivery",
            scope=scope,
            version=VersionRef(lineage_id="operation-lineage-a", revision=1),
            idempotency_key="operation-key-a",
        )
        task = TaskRef(
            task_id="task-a",
            owner="role_work",
            scope=scope,
            version=VersionRef(lineage_id="task-lineage-a", revision=2),
        )
        attempt = AttemptRef(attempt_id="attempt-a", operation=operation, ordinal=1)
        part = PartRef(part_id="part-a", operation=operation, sequence=1)

        self.assertFalse(source.is_expired_at(NOW + timedelta(minutes=4)))
        self.assertTrue(source.is_expired_at(NOW + timedelta(minutes=5)))
        self.assertEqual(asset.scope, scope)
        self.assertEqual(task.scope, scope)
        self.assertEqual(attempt.operation, operation)
        self.assertEqual(part.operation.idempotency_key, "operation-key-a")

    def test_audience_cannot_cross_installations_or_duplicate_subjects(self) -> None:
        scope = ScopeRef(
            installation_id="installation-alpha",
            platform="onebot",
            kind=ScopeKind.GROUP,
            native_scope_id="group-a",
        )
        local_subject = SubjectRef(
            installation_id="installation-alpha",
            kind=SubjectKind.HUMAN,
            subject_id="subject-a",
        )
        AudienceRef(scope=scope, recipients=(local_subject,))

        with self.assertRaises(ReferenceValidationError):
            AudienceRef(scope=scope, recipients=(local_subject, local_subject))
        with self.assertRaises(ReferenceValidationError):
            AudienceRef(
                scope=scope,
                recipients=(
                    SubjectRef(
                        installation_id="installation-beta",
                        kind=SubjectKind.HUMAN,
                        subject_id="subject-b",
                    ),
                ),
            )

    def test_references_reject_naive_expiry_timestamps(self) -> None:
        scope = ScopeRef(
            installation_id="installation-alpha",
            platform="onebot",
            kind=ScopeKind.PRIVATE,
            native_scope_id="private-a",
        )
        with self.assertRaises(ReferenceValidationError):
            SourceRef(
                source_id="source-a",
                owner="conversation",
                scope=scope,
                version=VersionRef(lineage_id="source-lineage-a", revision=1),
                issued_at=datetime(2026, 9, 21, 0, 0),
            )
