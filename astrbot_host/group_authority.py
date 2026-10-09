"""Atomic group admission and per-speaker grants for the foreground preview profile."""

from dataclasses import replace
from datetime import datetime

from companion_v2.adapters.astrbot.staging_config import REQUIRED_CAPABILITIES
from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.personas import PersonaBinding, SelectorKind
from companion_v2.memory.group.access import CAPABILITIES as GROUP_MEMORY_CAPABILITIES


OPTIONAL_CAPABILITIES = GROUP_MEMORY_CAPABILITIES | {"extension.tool.invoke", "role.expression.read"}


class GroupAuthority:
    def __init__(self, authority):
        self.authority = authority

    @staticmethod
    def grant_id(scope, subject, capability):
        return "host-group-grant:" + digest([scope.key, subject, capability])

    def select(self, target, captured):
        authority = self.authority
        authority.remember_target(target)
        scope, role, principal = captured.route.scope, captured.role, captured.principal
        if (scope.kind is not ScopeKind.GROUP or scope.installation_id != authority.runtime.installation_id
                or (scope.platform, scope.account_id, scope.bot_id, scope.native_scope_id)
                != (target.platform_id, target.account_id, target.bot_id, target.group_id)
                or captured.route.group_id != target.group_id or captured.route.user is not None
                or principal != authority.principal(target, principal.native_account_id)
                or not any(p.bot_id == target.bot_id and p.role_id == role.subject_id for p in authority.settings.personas)):
            raise TaskError("host_target_mismatch", "group scope, speaker and persona must retain their configured route")
        with authority.runtime.transaction():
            actor = authority.ensure_actor(target, principal.native_account_id)
            audience = group_audience(scope, actor.subject)
            if captured.recipients != audience:
                raise TaskError("host_group_audience_mismatch", "group input must retain its collective audience")
            route = authority.personas.register_route(captured.route, observed_at=authority.now())
            identifier = authority.binding_id(scope)
            at = datetime.fromisoformat(authority.require_manifest()["valid_from"])
            if authority.personas.binding(identifier) is None:
                selector = next(s for s, _ in route.selectors() if s.kind is SelectorKind.SESSION)
                authority.personas.set_binding(PersonaBinding(identifier, selector, role, 0, at,
                    "astrbot-multi-host", "configured-group-target"), expected_revision=0, observed_at=authority.now())
            resolved = require(authority.personas.resolve(scope, observed_at=authority.now()))
            if resolved.selected.binding_id != identifier or resolved.binding.role != role:
                raise TaskError("host_persona_binding_changed", "the configured group role binding changed")
            # Private memory/life/action grants are never inherited from private targets.
            for capability in sorted(REQUIRED_CAPABILITIES | OPTIONAL_CAPABILITIES):
                grant = self.grant_id(scope, actor.subject, capability)
                if authority.runtime.read_one("SELECT 1 FROM identity_grants WHERE grant_id = ?", (grant,)) is None:
                    authority.identities.issue_grant(grant_id=grant, subject=actor.subject, scope=scope,
                        capability=capability, tier=AuthorizationTier.STANDARD, valid_from=at,
                        expected_revision=authority.identities.revision)
                if capability in OPTIONAL_CAPABILITIES:
                    continue  # Revoked optional tool rights do not block ordinary group conversation.
                access = require(authority.identities.authorize(actor, scope=scope, capability=capability, observed_at=authority.now()))
                if access.grant_id != grant:
                    raise TaskError("host_grant_changed", "the original group grant is no longer current")
            # Different speakers share a group conversation. AstrBot unique-session
            # mode instead gives each speaker its own persona selection/fence.
            key = "host.group.active:" + digest([target.target_id, scope.session_id])
            old = authority.read(key)
            if old and old != scope.document():
                previous = authority.personas.binding(authority.binding_id(ScopeRef.restore(old)))
                if previous is not None:
                    authority.personas.set_binding(replace(previous, revision=previous.revision + 1),
                        expected_revision=previous.revision, observed_at=authority.now())
            authority.write(key, scope.document())
            return TaskContext(actor, resolved.binding, audience)
