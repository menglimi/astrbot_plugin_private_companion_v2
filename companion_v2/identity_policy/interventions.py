"""Exact-window permissions for user-triggered role state and schedule changes."""

from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.refs import ScopeKind, SubjectKind
from companion_v2.identity_policy.models import AuthorizationTier


STATE_INTERVENTION = "role.state.intervene"
CALENDAR_INTERVENTION = "calendar.intervene"
REST_WAKE_INTERVENTION = "role.rest.wake"
INTERVENTION_CAPABILITIES = (
    STATE_INTERVENTION,
    CALENDAR_INTERVENTION,
    REST_WAKE_INTERVENTION,
)


def _tier(runtime, subject):
    row = runtime.read_one(
        "SELECT tier FROM subject_access_tiers WHERE subject_kind = ? AND subject_id = ?",
        (subject.kind.value, subject.subject_id),
    )
    return AuthorizationTier(row["tier"]) if row else AuthorizationTier.STANDARD


def authorized_capabilities(tasks, context, *, at):
    """Return capabilities granted to this authenticated person in this exact window."""
    if (context.scope.kind is not ScopeKind.PRIVATE
            or context.actor.subject.kind is not SubjectKind.HUMAN
            or context.audience.recipients != (context.actor.subject,)):
        return frozenset()
    try:
        require(tasks.check_context_access(context, action="conversation.reply", observed_at=at))
        if _tier(tasks.runtime, context.actor.subject) is AuthorizationTier.CORE:
            return frozenset(INTERVENTION_CAPABILITIES)
        return frozenset(capability for capability in INTERVENTION_CAPABILITIES
            if tasks.identity.authorize(context.actor, scope=context.scope,
                capability=capability, observed_at=at).is_success)
    except TaskError:
        return frozenset()


def has_capability(tasks, context, capability, *, at):
    if capability not in INTERVENTION_CAPABILITIES:
        return False
    return capability in authorized_capabilities(tasks, context, at=at)


def require_capability(tasks, context, capability, *, at):
    if not has_capability(tasks, context, capability, at=at):
        raise TaskError("role_intervention_permission_required",
                        "the current private participant is not authorized for this role intervention")
