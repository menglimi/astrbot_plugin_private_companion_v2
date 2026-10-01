from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.capabilities import (
    CapabilityAuthorizationState, CapabilityPackageDescriptor, CapabilityRepository, FurnitureDescriptor,
)
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.directory import IdentityDirectory
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.screen.models import SCREEN_EXTENSION, SCREEN_PROCESS, SCREEN_READ
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
INSTALLATION = "installation-g6"


def descriptor(version: str = "1.0.0") -> CapabilityPackageDescriptor:
    return CapabilityPackageDescriptor(
        extension_id=SCREEN_EXTENSION, package_id="companion.screen-package", publisher_id="companion",
        package_version=version, artifact_hash=f"fixture-hash-{version}",
        capabilities=(SCREEN_READ, SCREEN_PROCESS), dataset_owners=("screen",),
        furniture=(FurnitureDescriptor("screen-monitor", SCREEN_EXTENSION, "Monitor", "screen-panel"),),
    )


class G6Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory(prefix="companion-v2-g6-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.runtime = self.open_runtime()
        self.capabilities = CapabilityRepository(self.runtime)
        self.scope = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "private-a")
        self.subject = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "subject-a")
        self.role = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-a")
        self.principal = AuthenticatedHostPrincipal(INSTALLATION, "fixture-host", "onebot", "account-a")
        self.identities = IdentityDirectory()
        self.clock = DeterministicClock.at(NOW)
        self.identities.bind(
            binding_id="binding-a", principal=self.principal, subject=self.subject,
            valid_from=NOW - timedelta(minutes=1),
        )
        for capability in (SCREEN_READ, SCREEN_PROCESS):
            self.identities.issue_grant(
                grant_id=f"grant-{capability}", subject=self.subject, scope=self.scope, capability=capability,
                tier=AuthorizationTier.IMPORTANT, valid_from=NOW - timedelta(minutes=1),
            )
        self.resolved = self.identities.resolve_authenticated(self.principal, observed_at=NOW).unwrap()

    def open_runtime(self) -> StorageRuntime:
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def install(self) -> None:
        selected = descriptor()
        self.capabilities.register_descriptor(selected, registered_at=NOW).unwrap()
        self.capabilities.acquire(
            extension_id=SCREEN_EXTENSION, package_id=selected.package_id, package_version=selected.package_version,
            expected_revision=0, observed_at=NOW,
        ).unwrap()

    def enable_screen(self) -> None:
        self.install()
        self.capabilities.set_role_enabled(
            extension_id=SCREEN_EXTENSION, role=self.role, enabled=True, expected_revision=0, observed_at=NOW,
        ).unwrap()
        for capability in (SCREEN_READ, SCREEN_PROCESS):
            self.capabilities.set_authorization(
                extension_id=SCREEN_EXTENSION, capability_id=capability, subject=self.subject,
                scope=self.scope, state=CapabilityAuthorizationState.ACTIVE,
                expected_revision=0, observed_at=NOW,
            ).unwrap()
