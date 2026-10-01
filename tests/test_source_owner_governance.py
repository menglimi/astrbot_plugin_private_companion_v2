"""A closed/missing owner cannot make a persisted derived source readable again."""

import unittest

from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import AudienceRef, SourceRef, VersionRef
from companion_v2.sources.dependencies import link
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import SourceRepository
from tests.test_management_access import ManagementFixture, NOW, SCOPE


class SourceOwnerGovernanceTests(ManagementFixture):
    def publish(self, repository, identifier, owner="guarded.owner"):
        reference = SourceRef(identifier, owner, SCOPE, VersionRef(identifier, 1), NOW)
        record = SourceRecord(reference, AudienceRef(SCOPE, (self.important.subject,)), digest(identifier), identifier)
        repository.publish(record, observed_at=NOW).unwrap()
        return reference

    def test_unloaded_owner_blocks_whole_dependency_chain_and_restart(self):
        repository = SourceRepository(self.runtime)
        guard = bind(self.runtime, "guarded.owner", lambda record, at: None)
        root = self.publish(repository, "root")
        derived = self.publish(repository, "derived", "derived.owner")
        leaf = self.publish(repository, "leaf", "leaf.owner")
        link(self.runtime, derived, (root,), NOW)
        link(self.runtime, leaf, (derived,), NOW)
        repository.validate_reference(leaf, observed_at=NOW).unwrap()
        guard.close()
        self.assertEqual(repository.validate_reference(leaf, observed_at=NOW).failure.code, "source_owner_unavailable")
        restored = self.open_runtime()
        sources = SourceRepository(restored)
        self.assertEqual(sources.validate_reference(leaf, observed_at=NOW).failure.code, "source_owner_unavailable")
        new_guard = bind(restored, "guarded.owner", lambda record, at: None)
        self.addCleanup(new_guard.close)
        sources.validate_reference(leaf, observed_at=NOW).unwrap()

    def test_old_close_cannot_remove_replacement_and_revocation_never_reactivates(self):
        repository = SourceRepository(self.runtime)
        old = bind(self.runtime, "guarded.owner", lambda record, at: None)
        root = self.publish(repository, "root")
        current = bind(self.runtime, "guarded.owner", lambda record, at: None)
        self.addCleanup(current.close)
        old.close()
        repository.validate_reference(root, observed_at=NOW).unwrap()
        repository.revoke(root, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(repository.validate_reference(root, observed_at=NOW).failure.code, "source_revoked")

    def test_owner_check_is_current_and_cannot_defer_authorization(self):
        repository = SourceRepository(self.runtime)
        allowed = True
        def check(record, at):
            if not allowed:
                raise TaskError("owner_withdrawn", "synthetic owner withdrew")
        current = bind(self.runtime, "guarded.owner", check)
        self.addCleanup(current.close)
        root = self.publish(repository, "root")
        repository.validate_reference(root, observed_at=NOW).unwrap()
        allowed = False
        self.assertEqual(repository.validate_reference(root, observed_at=NOW).failure.code, "owner_withdrawn")
        async def deferred(record, at):
            return None
        with self.assertRaises(ValueError):
            bind(self.runtime, "guarded.owner", deferred)


if __name__ == "__main__":
    unittest.main()
