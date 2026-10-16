"""Role-wide state injection with current reply authorization."""

from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.refs import ScopeKind, SubjectKind
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.identity_policy.private_domain import PrivateDomainAccess


class RoleStateAccess(PrivateDomainAccess):
    def __init__(self, tasks, read_settings):
        super().__init__(tasks)
        self.read_settings = read_settings

    def check_injection(self, context, *, at=None):
        at = at or self.tasks.now()
        private_owner = (
            context.scope.kind is ScopeKind.PRIVATE
            and context.actor.subject.kind is SubjectKind.HUMAN
            and context.audience.recipients == (context.actor.subject,)
        )
        group_reply = False
        if (context.scope.kind is ScopeKind.GROUP
                and context.actor.subject.kind is SubjectKind.HUMAN):
            try:
                group_reply = context.audience == group_audience(context.scope, context.actor.subject)
            except ValueError:
                group_reply = False
        if group_reply:
            require(self.tasks.check_context_access(
                context, action="conversation.reply", observed_at=at))
            settings, _ = self.read_settings(context)
            if settings["enabled"]:
                return
            raise TaskError("role_state_disabled", "role state reading is disabled")
        if private_owner:
            require(self.tasks.check_context_access(
                context, action="conversation.reply", observed_at=at))
            settings, _ = self.read_settings(context)
            if settings["enabled"]:
                return
        super().check(context, "role.state.read", at=at)
