"""Explicit game permissions for one host-resolved private conversation."""

from companion_v2.capabilities.models import CapabilityAuthorizationState, CapabilityDesiredState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import OperationRef, ScopeKind, VersionRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.storage.codec import scope_values
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from .provider import (TICTACTOE_ACTIONS, GOMOKU_ACTIONS, XIANGQI_ACTIONS, TURTLE_ACTIONS,
                       DRAW_ACTIONS, PIG_READ, PIG_CREATE, PIG_ROLL, PIG_HOLD, PIG_CLOSE,
                       BLACKJACK_READ, BLACKJACK_CREATE, BLACKJACK_HIT, BLACKJACK_STAND, BLACKJACK_CLOSE,
                       PLUGIN_ID)

GROUPS = {
    "tictactoe": TICTACTOE_ACTIONS, "gomoku": GOMOKU_ACTIONS,
    "pig_dice": {PIG_READ, PIG_CREATE, PIG_ROLL, PIG_HOLD, PIG_CLOSE},
    "blackjack": {BLACKJACK_READ, BLACKJACK_CREATE, BLACKJACK_HIT, BLACKJACK_STAND, BLACKJACK_CLOSE},
    "xiangqi": XIANGQI_ACTIONS, "turtle_soup": TURTLE_ACTIONS, "draw_guess": DRAW_ACTIONS,
}
OWNER = "game.access"


class NativeGameAccess:
    def __init__(self, application, context, package):
        self.application, self.context, self.package = application, context, package
        self.runtime = application.runtime
        self.repository = CapabilityRepository(self.runtime)
        self.identities = PersistentIdentityDirectory(self.runtime)
        self.policy = ObjectAccessPolicy(self.runtime)
        if package.extension_id != "game" or package.package_id != PLUGIN_ID:
            raise TaskError("game_provider_changed", "the loaded native game package changed")

    def _access(self, operator, at, action="capability.view"):
        context = self.context
        if context.scope.kind is not ScopeKind.PRIVATE:
            raise TaskError("game_private_required", "select a bound private conversation")
        require(self.application.tasks.authorize_context(context, action="conversation.reply", observed_at=at))
        require(self.policy.authorize(operator, scope=context.scope, action=action,
                                      owner=context.actor.subject, observed_at=at))

    def _state(self):
        context = self.context
        result = self.repository.installation(extension_id="game")
        installed = result.unwrap() if result.is_success else None
        selection = (require(self.repository.projection(extension_id="game",
            role=context.role_binding.role, scope=context.scope)).role_selection if installed else None)
        rows = self.runtime.read_all("""SELECT capability_id, state, revision FROM capability_authorizations
            WHERE extension_id = 'game' AND subject_kind = ? AND subject_id = ?
              AND installation_id = ? AND platform = ? AND scope_kind = ? AND native_scope_id = ?
              AND bot_id = ? AND account_id = ? AND conversation_id = ? AND session_id = ?
            ORDER BY capability_id""", (context.actor.subject.kind.value, context.actor.subject.subject_id,
                                          *scope_values(context.scope)))
        return installed, selection, {row["capability_id"]: dict(row) for row in rows}

    def _token(self, state):
        return digest([self.context.key, encode(self.package),
            [encode(item) if item is not None else None for item in state],
            self.identities.revision, self.policy.revision])

    def status(self, operator, at):
        self._access(operator, at)
        with self.runtime.read_snapshot():
            state = self._state()
            installed, selection, grants = state
            same = bool(installed and (installed.package_id, installed.package_version, installed.artifact_hash)
                == (self.package.package_id, self.package.package_version, self.package.artifact_hash))
            active = bool(same and installed.desired_state is CapabilityDesiredState.ACTIVE)
            external = self.application.external
            available = {tool.action for tool in external.catalog_for(self.context)} if external else set()
            games = [{"game_type": kind,
                "consented": all(grants.get(action, {}).get("state") == "active" for action in actions),
                "invokable": actions.issubset(available)} for kind, actions in GROUPS.items()]
            return {"package_version": self.package.package_version, "active": active,
                "role_enabled": bool(selection and selection.enabled), "games": games,
                "can_manage": self.policy.scope_access(operator, scope=self.context.scope,
                    action="capability.role.set", observed_at=at, core_only=True).is_success,
                "edit_token": self._token(state)}

    def configure(self, operator, command, at):
        self._access(operator, at, "capability.consent.set")
        require(self.policy.scope_access(operator, scope=self.context.scope,
            action="capability.role.set", observed_at=at, core_only=True))
        if (type(command) is not dict or set(command) != {"operation_key", "edit_token", "game_type", "enabled"}
                or type(command["game_type"]) is not str or command["game_type"] not in GROUPS
                or type(command["enabled"]) is not bool
                or any(type(command[key]) is not str or not command[key].strip() or len(command[key]) > 160
                       for key in ("operation_key", "edit_token"))):
            raise TaskError("game_access_request_invalid", "an explicit scoped game permission is required")
        context = self.context
        key = digest([context.key, operator.subject.subject_id, command["operation_key"]])
        operation = OperationRef("game-access:" + key, OWNER, context.scope, VersionRef(key, 1), key)
        operations = OperationRepository(self.runtime)
        with self.runtime.transaction():
            receipt = require(operations.reserve(operation,
                parameter_hash=digest([encode(operator.principal), encode(operator.subject),
                    operator.binding_id, operator.binding_revision, context.key, command]), observed_at=at))
            if receipt.replayed:
                if receipt.state is not OperationState.COMPLETED:
                    raise TaskError("capability_operation_unresolved", "the original permission request is unresolved")
                return {"replayed": True, "status": self.status(operator, at)}
            state = self._state()
            if command["edit_token"] != self._token(state):
                raise TaskError("game_access_changed", "refresh changed permissions before saving")
            installed, selection, grants = state
            enabled = command["enabled"]
            if enabled:
                require(self.repository.register_descriptor(self.package, registered_at=at))
                if installed is None:
                    installed = require(self.repository.acquire(extension_id="game", package_id=self.package.package_id,
                        package_version=self.package.package_version, expected_revision=0, observed_at=at))
                if (installed.package_id, installed.package_version, installed.artifact_hash) != (
                        self.package.package_id, self.package.package_version, self.package.artifact_hash):
                    raise TaskError("game_provider_changed", "the installed native game package changed")
                if installed.desired_state is not CapabilityDesiredState.ACTIVE:
                    raise TaskError("capability_not_active", "enable the game module first")
                if not selection or not selection.enabled:
                    require(self.repository.set_role_enabled(extension_id="game", role=context.role_binding.role,
                        bot_id=context.scope.bot_id, enabled=True,
                        expected_revision=selection.revision if selection else 0, observed_at=at))
                if not self.identities.authorize(context.actor, scope=context.scope,
                        capability="extension.tool.invoke", observed_at=at).is_success:
                    binding = next(item for item in self.identities.snapshot().bindings
                                   if item.binding_id == context.actor.binding_id)
                    self.identities.issue_grant(grant_id="game-invoke:" + key, subject=context.actor.subject,
                        scope=context.scope, capability="extension.tool.invoke", tier=AuthorizationTier.STANDARD,
                        valid_from=at, expires_at=binding.expires_at, expected_revision=self.identities.revision)
            if installed:
                for action in sorted(GROUPS[command["game_type"]]):
                    require(self.repository.set_authorization(extension_id="game", capability_id=action,
                        subject=context.actor.subject, scope=context.scope,
                        state=CapabilityAuthorizationState.ACTIVE if enabled else CapabilityAuthorizationState.REVOKED,
                        expected_revision=grants.get(action, {}).get("revision", 0), observed_at=at))
            require(operations.transition(operation.operation_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=at))
            return {"replayed": False, "status": self.status(operator, at)}
