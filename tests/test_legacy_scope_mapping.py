from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.refs import AudienceRef, ScopeKind, ScopeRef, SourceRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.legacy.scope_mapping import LegacyScopeMapping, LegacyScopeMappingDirectory
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal
from companion_v2.identity_policy.personas import ConversationRoute, PersonaDirectory
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc)
INSTALLATION = "legacy-mapping-installation"
ORIGINAL = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "old-window")
RESOLVED = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "old-window",
                    "bot-a", "login-a", "conversation-a", "session-a")
USER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-a")


class LegacyScopeMappingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-legacy-map-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.sources = SourceRepository(self.runtime)
        self.directory = LegacyScopeMappingDirectory(self.runtime, self.sources)
        self.identities = PersistentIdentityDirectory(self.runtime)
        principal = AuthenticatedHostPrincipal(INSTALLATION, "host", "onebot", "native-user", "bot-a", "login-a")
        self.identities.bind(binding_id="mapping-user", principal=principal, subject=USER, valid_from=NOW, expected_revision=1)
        self.actor = self.identities.resolve_authenticated(principal, observed_at=NOW).unwrap()
        PersonaDirectory(self.runtime).register_route(ConversationRoute(RESOLVED, user=USER), observed_at=NOW)

    def evidence(self, *, expires_at=None):
        reference = SourceRef("mapping-evidence", "legacy.identity-map", RESOLVED,
                              VersionRef("mapping-evidence", 1), NOW, expires_at)
        self.sources.publish(SourceRecord(reference, AudienceRef(RESOLVED, (USER,)), "hash", "signed fixture"),
                             observed_at=NOW).unwrap()
        return reference

    def mapping(self, evidence):
        return LegacyScopeMapping("mapping-a", ORIGINAL, RESOLVED, evidence, "trusted-import", 1, NOW, self.actor)

    def test_mapping_requires_current_evidence_and_survives_restart(self):
        evidence = self.evidence()
        self.directory.register(self.mapping(evidence), observed_at=NOW).unwrap()
        self.assertEqual(self.directory.resolve(ORIGINAL, observed_at=NOW).unwrap(), RESOLVED)
        self.runtime.close()
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        reopened = LegacyScopeMappingDirectory(self.runtime, SourceRepository(self.runtime))
        self.assertEqual(reopened.resolve(ORIGINAL, observed_at=NOW).unwrap(), RESOLVED)

    def test_revoked_or_expired_evidence_does_not_get_replaced_by_current_route(self):
        evidence = self.evidence(expires_at=NOW + timedelta(minutes=2))
        self.directory.register(self.mapping(evidence), observed_at=NOW).unwrap()
        self.assertEqual(self.directory.resolve(ORIGINAL, observed_at=NOW + timedelta(minutes=2)).failure.code,
                         "legacy_mapping_evidence_unavailable")
        self.sources.revoke(evidence, expected_governance_revision=1,
                            observed_at=NOW + timedelta(minutes=1)).unwrap()
        self.assertEqual(self.directory.resolve(ORIGINAL, observed_at=NOW + timedelta(minutes=1)).failure.code,
                         "legacy_mapping_evidence_unavailable")

    def test_mapping_revocation_returns_to_unresolved(self):
        evidence = self.evidence()
        self.directory.register(self.mapping(evidence), observed_at=NOW).unwrap()
        self.directory.revoke("mapping-a", expected_revision=1, observed_at=NOW + timedelta(minutes=1))
        self.assertEqual(self.directory.resolve(ORIGINAL, observed_at=NOW + timedelta(minutes=1)).failure.code,
                         "scope_unresolved")

    def test_rebinding_same_external_account_does_not_transfer_mapping(self):
        self.directory.register(self.mapping(self.evidence()), observed_at=NOW).unwrap()
        self.identities.bind(binding_id="rebound-user", principal=self.actor.principal,
            subject=SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-b"), valid_from=NOW,
            expected_revision=self.identities.revision)
        self.assertEqual(self.directory.resolve(ORIGINAL, observed_at=NOW).failure.code,
                         "legacy_mapping_identity_changed")

    def test_forged_reference_cannot_extend_evidence_expiry_or_replace_its_version(self):
        evidence = self.evidence(expires_at=NOW + timedelta(minutes=1))
        for changed in (replace(evidence, expires_at=None), replace(evidence, version=VersionRef("mapping-evidence", 2))):
            self.assertEqual(self.directory.register(self.mapping(changed), observed_at=NOW).failure.code,
                             "legacy_mapping_evidence_unavailable")
        self.assertEqual(self.runtime.read_all("SELECT * FROM legacy_scope_mappings", ()), ())

    def test_conflicting_active_mappings_are_not_arbitrarily_selected(self):
        mapping = self.mapping(self.evidence())
        self.directory.register(mapping, observed_at=NOW).unwrap()
        self.directory.register(replace(mapping, mapping_id="mapping-b"), observed_at=NOW).unwrap()
        self.assertEqual(self.directory.resolve(ORIGINAL, observed_at=NOW).failure.code, "legacy_scope_mapping_conflict")


if __name__ == "__main__":
    unittest.main()
