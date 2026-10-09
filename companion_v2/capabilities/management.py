"""One authenticated local management service for page, command and tool adapters.

The service records catalog choices and consent only. A completed local operation
does not claim a package was downloaded, loaded, or removed by a host.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable

from companion_v2.configuration.models import fingerprint
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import OperationRef, ReferenceValidationError, ScopeKind, ScopeRef, SubjectRef
from companion_v2.identity_policy.models import AuthorizationTier, ResolvedIdentity
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository
from companion_v2.storage.runtime import StorageRuntime

from .models import CapabilityAuthorization, CapabilityAuthorizationState, CapabilityProjection, _opaque
from .repositories import CapabilityRepository


class ManagementError(ValueError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code


def _require(result: Outcome):
    if result.failure:
        raise ManagementError(result.failure.code, result.failure.reason)
    return result.unwrap()


@dataclass(frozen=True)
class CapabilityCommandReceipt:
    operation: OperationRef
    action: str
    extension_id: str
    replayed: bool
    effect: str = "local_record_saved"


class CapabilityManagementService:
    OWNER = "capability.management"

    def __init__(self, runtime: StorageRuntime) -> None:
        self.runtime = runtime
        self.policy = ObjectAccessPolicy(runtime)
        self.repository = CapabilityRepository(runtime)
        self.operations = OperationRepository(runtime)

    def management_scope(self, extension_id: str) -> ScopeRef:
        _opaque(extension_id, field="extension_id")
        return ScopeRef(self.runtime.installation_id, "companion", ScopeKind.SYSTEM,
                        "capability." + fingerprint(extension_id))

    def _command(
        self, actor: ResolvedIdentity, *, extension_id: str, action: str, scope: ScopeRef,
        operation: OperationRef, parameters: dict, mutate: Callable[[], Outcome], observed_at: datetime,
        owner: SubjectRef | None = None,
    ) -> Outcome[CapabilityCommandReceipt]:
        try:
            with self.runtime.transaction():
                access = (self.policy.scope_access(actor, scope=scope, action=action, observed_at=observed_at)
                          if owner is None else self.policy.authorize(
                              actor, scope=scope, action=action, owner=owner, observed_at=observed_at))
                _require(access)
                if operation.owner != self.OWNER or operation.scope != scope:
                    raise ManagementError("operation_scope_mismatch", "operation must target this capability management scope")
                reservation = _require(self.operations.reserve(operation, parameter_hash=fingerprint({
                    "extension_id": extension_id, "action": action, "parameters": parameters,
                    "actor": [asdict(actor.principal), asdict(actor.subject), actor.binding_id, actor.binding_revision],
                }), observed_at=observed_at))
                if reservation.replayed:
                    if reservation.state is not OperationState.COMPLETED:
                        raise ManagementError("capability_operation_unresolved", "original local operation has no confirmed completion")
                else:
                    _require(mutate())
                    _require(self.operations.transition(reservation.operation.operation_id,
                            expected_state=OperationState.ACCEPTED, next_state=OperationState.COMPLETED,
                            observed_at=observed_at))
                return Outcome.success(CapabilityCommandReceipt(reservation.operation, action, extension_id, reservation.replayed))
        except ManagementError as error:
            return Outcome.failed(error.code, str(error))

    def select_package(
        self, actor: ResolvedIdentity, *, extension_id: str, action: str, package_id: str, package_version: str,
        artifact_hash: str, expected_revision: int, operation: OperationRef, observed_at: datetime,
    ) -> Outcome[CapabilityCommandReceipt]:
        if action not in ("acquire", "update"):
            return Outcome.failed("unknown_access_action", "only fixed catalog acquisition or update is supported")

        def mutate():
            selected = _require(self.repository.descriptor(extension_id=extension_id,
                                package_id=package_id, package_version=package_version))
            if selected.artifact_hash != artifact_hash:
                raise ManagementError("capability_artifact_mismatch", "selected package content differs from the reviewed catalog entry")
            method = self.repository.acquire if action == "acquire" else self.repository.update
            return method(extension_id=extension_id, package_id=package_id, package_version=package_version,
                          expected_revision=expected_revision, observed_at=observed_at)

        return self._command(actor, extension_id=extension_id, action="capability." + action,
            scope=self.management_scope(extension_id), operation=operation, observed_at=observed_at, mutate=mutate,
            parameters={"package_id": package_id, "package_version": package_version, "artifact_hash": artifact_hash,
                        "expected_revision": expected_revision})

    def change_lifecycle(
        self, actor: ResolvedIdentity, *, extension_id: str, action: str, expected_revision: int,
        operation: OperationRef, observed_at: datetime,
    ) -> Outcome[CapabilityCommandReceipt]:
        methods = {"pause": self.repository.pause, "resume": self.repository.resume,
                   "discard.request": self.repository.request_discard}
        if action not in methods:
            return Outcome.failed("unknown_access_action", "lifecycle action is not a user management operation")
        return self._command(actor, extension_id=extension_id, action="capability." + action,
            scope=self.management_scope(extension_id), operation=operation, observed_at=observed_at,
            parameters={"expected_revision": expected_revision},
            mutate=lambda: methods[action](extension_id=extension_id, expected_revision=expected_revision, observed_at=observed_at))

    def uninstall(
        self, actor: ResolvedIdentity, *, extension_id: str, expected_revision: int,
        operation: OperationRef, observed_at: datetime,
    ) -> Outcome[CapabilityCommandReceipt]:
        """Detach an extension atomically while retaining its V2-owned records."""
        def detach():
            requested = self.repository.request_discard(
                extension_id=extension_id, expected_revision=expected_revision, observed_at=observed_at)
            if requested.failure is not None:
                return requested
            return self.repository.complete_discard(
                extension_id=extension_id, expected_revision=requested.unwrap().revision, observed_at=observed_at)

        return self._command(actor, extension_id=extension_id, action="capability.discard.request",
            scope=self.management_scope(extension_id), operation=operation, observed_at=observed_at,
            parameters={"expected_revision": expected_revision, "uninstall": True}, mutate=detach)

    def role_scope(self, extension_id: str, role: SubjectRef, bot_id: str) -> ScopeRef:
        _opaque(extension_id, field="extension_id")
        _opaque(bot_id, field="bot_id")
        return ScopeRef(role.installation_id, "companion", ScopeKind.SYSTEM,
                        "capability.role." + fingerprint([extension_id, role.subject_id]), bot_id=bot_id)

    def set_role_enabled(
        self, actor: ResolvedIdentity, *, extension_id: str, role: SubjectRef, bot_id: str, enabled: bool,
        expected_revision: int, operation: OperationRef, observed_at: datetime,
    ) -> Outcome[CapabilityCommandReceipt]:
        return self._command(actor, extension_id=extension_id, action="capability.role.set",
            scope=self.role_scope(extension_id, role, bot_id), operation=operation, observed_at=observed_at,
            parameters={"role": asdict(role), "bot_id": bot_id, "enabled": enabled, "expected_revision": expected_revision},
            mutate=lambda: self.repository.set_role_enabled(extension_id=extension_id, role=role, bot_id=bot_id,
                            enabled=enabled, expected_revision=expected_revision, observed_at=observed_at))

    def set_consent(
        self, actor: ResolvedIdentity, *, extension_id: str, capability_id: str, subject: SubjectRef, scope: ScopeRef,
        state: CapabilityAuthorizationState, expected_revision: int, operation: OperationRef, observed_at: datetime,
    ) -> Outcome[CapabilityCommandReceipt]:
        if not isinstance(state, CapabilityAuthorizationState):
            raise ReferenceValidationError("consent state must be explicit")
        return self._command(actor, extension_id=extension_id, action="capability.consent.set", scope=scope, owner=subject,
            operation=operation, observed_at=observed_at,
            parameters={"capability_id": capability_id, "subject": asdict(subject),
                        "state": state.value, "expected_revision": expected_revision},
            mutate=lambda: self.repository.set_authorization(extension_id=extension_id, capability_id=capability_id,
                            subject=subject, scope=scope, state=state, expected_revision=expected_revision, observed_at=observed_at))

    def projection(
        self, actor: ResolvedIdentity, *, extension_id: str, observed_at: datetime,
        role: SubjectRef | None = None, scope: ScopeRef | None = None,
    ) -> Outcome[CapabilityProjection]:
        with self.runtime.read_snapshot():
            access = self.policy.scope_access(actor, scope=scope or self.management_scope(extension_id),
                        action="capability.view", observed_at=observed_at, allow_private_owner=True)
            if access.failure:
                return Outcome(failure=access.failure)
            if role is not None:
                if scope is None or not scope.is_resolved:
                    return Outcome.failed("scope_unresolved", "role capability view requires its complete bot/account scope")
                if access.unwrap().tier is not AuthorizationTier.CORE:
                    current = self.policy.identity.resolve_role(scope, observed_at=observed_at)
                    if current.failure:
                        return Outcome(failure=current.failure)
                    if current.unwrap().role != role:
                        return Outcome.failed("role_binding_changed", "capability view belongs to another role")
            return self.repository.projection(extension_id=extension_id, role=role, scope=scope)

    def own_consent(
        self, actor: ResolvedIdentity, *, extension_id: str, capability_id: str,
        scope: ScopeRef, observed_at: datetime,
    ) -> Outcome[CapabilityAuthorization]:
        """Read only the authenticated caller's retained consent, without enabling it."""
        with self.runtime.read_snapshot():
            access = self.policy.scope_access(actor, scope=scope, action="capability.view",
                                             observed_at=observed_at, allow_private_owner=True)
            if access.failure:
                return Outcome(failure=access.failure)
            return self.repository.consent(extension_id=extension_id, capability_id=capability_id,
                                           subject=actor.subject, scope=scope)
