"""Group text and original images retain the speaker and collective audience."""

from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.group_audience import group_audience
from .native import account_number
from companion_v2.adapters.astrbot.onebot import OneBotTextSender


class OneBotGroupSender(OneBotTextSender):
    supports_images = True

    def route(self, context):
        scope = context.scope
        sender = account_number(context.actor.principal.native_account_id)
        group = account_number(scope.native_scope_id)
        if (scope.kind is not ScopeKind.GROUP or sender == scope.account_id
                or scope.session_id not in (group, sender + "_" + group)
                or context.audience != group_audience(scope, context.actor.subject)):
            raise ValueError("group delivery requires the original group, speaker session and collective audience")
        return "send_group_msg", {"group_id": int(group)}
