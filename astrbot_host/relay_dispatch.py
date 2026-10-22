"""跨窗口递话的宿主侧发送：按 plan_relay 的结论决定发不发、发什么。

学 V1 的做法：V1 的 atrelay 就是拿目标私聊 id 直接调 OneBot 的
`send_private_msg`。V2 已经有同样的原语——`private_notice.send_private_notice`
（`call_action("send_private_msg", self_id=..., user_id=...)`），所以这里不重造
发送通道，只补三件 V1 没有严格做好的事：

1. **先判定再发送**：一律经过 `plan_relay`，未通过就只返回拒绝码，不触网；
2. **管理员路径必须带确认**：`needs_confirm=True` 且没有 `confirmed=True` 时
   只回一条待确认结果，绝不发送；
3. **审计**：把计划里的 audit 字段原样返回，由调用方写入 outbox。

这个模块只做"一次递话"，不订阅事件、不注册工具——接入点由调用方决定。
"""

from companion_v2.conversation.relay import plan_relay
from companion_v2.conversation.relay_policy import RelayRequest

from .private_notice import send_private_notice


class RelayNotDelivered(Exception):
    """递话没有被送出去（未通过判定、待确认或发送失败）。"""

    def __init__(self, code, message, *, audit=None, needs_confirm=False):
        super().__init__(message)
        self.code = code
        self.audit = audit or {}
        self.needs_confirm = needs_confirm


def with_destination(route, destination_id):
    """把一条已认证路由的对方 id 换掉，其余（账号、平台、客户端）保持不变。"""
    from dataclasses import replace
    try:
        return replace(route, peer=str(destination_id))
    except (TypeError, ValueError):
        from types import SimpleNamespace
        values = dict(vars(route)) if hasattr(route, "__dict__") else {}
        values["peer"] = str(destination_id)
        return SimpleNamespace(**values)


async def relay_private(controller, event, *, request: RelayRequest, settings,
                        actor_is_core: bool, actor_id: str = "", confirmed: bool = False,
                        route=None, base_route=None, transport=None):
    """把一条私聊递话发出去，或返回"还需要确认"。

    ``route`` 由调用方用现有的路由鉴权（`recalls.authenticate_notice_route`
    那套）解析好传进来；本函数不自己猜目标，避免把内容发到未授权窗口。
    """
    plan = plan_relay(request, settings, actor_is_core=actor_is_core, actor_id=actor_id)
    if not plan.allowed:
        raise RelayNotDelivered(plan.decision.code, plan.decision.reason, audit=plan.audit)
    if plan.needs_confirm and not confirmed:
        # 管理员的递话要先确认：这里不发，只把待确认的事实交回调用方。
        raise RelayNotDelivered("relay_confirmation_required",
                                "这段递话需要先确认，确认后才会发送。",
                                audit=plan.audit, needs_confirm=True)
    if route is None and base_route is not None:
        # 同一个 Bot 账号、只换对方 id：复用已认证事件里的 platform/login/client，
        # 不让递话自己去找账号或客户端（那等于凭空扩大发送能力）。
        route = with_destination(base_route, plan.destination_id)
    if route is None:
        raise RelayNotDelivered("relay_target_unavailable", "目标私聊不可用，未发送。",
                                audit=plan.audit)
    receipt = await send_private_notice(controller, event, text=plan.text, route=route, transport=transport)
    if receipt.get("state") != "delivered" or receipt.get("message_id") is None:
        return {"state": "unknown", "text": plan.text, "audit": plan.audit, "receipt": receipt}
    return {"state": "sent", "text": plan.text, "audit": plan.audit, "receipt": receipt}


__all__ = ["RelayNotDelivered", "relay_private", "with_destination"]
