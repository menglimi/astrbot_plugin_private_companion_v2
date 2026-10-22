"""把"没有对话权限"那一句话真的发出去。

为什么这一句不走核心投递通道（``companion_v2/delivery``）：那条通道要求一次
已解析的 ``TaskContext`` 和一项按人签发的能力 grant（``DeliveryOwner.action``），
而我们要回话的对象恰恰是**没有**对话权限的人，甚至是**没有任何身份**的陌生号
（未绑定账号没有 subject、没有 scope、没有人格路由）。所以这句话在这里用平台
反向 WebSocket 直接发一次纯文本——与 ``pokes.py`` 里那半句回话同一种形状。

三条硬约束：

* **只在真实投递模式下才可能发**：现在"真实投递"是唯一模式（正式版已删除预览档），
  所以这句话总是允许发出；`private_notice_allowed` 是唯一的判断点。
* **只发这一行**：不读记忆、不调模型、不建身份、不签发 grant、不写对话表。
* **不重放未知结果**：平台调用抛错就是"没发出去"，记一次失败，不重试；
  冷却由 ``PrivateRefusalNotice`` 负责，避免同一个人被反复打扰。
"""

from __future__ import annotations

from collections.abc import Mapping

from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import ScopeKind


async def send_text_notice(controller, route, *, text, transport=None):
    """平台直发一句纯文本到已认证的路由（私聊或群），返回有界回执。"""
    if not text or not str(text).strip():
        return {"state": "skipped", "reason": "blank_line"}
    api = transport if transport is not None else _transport(controller, route)
    if route.kind is ScopeKind.GROUP:
        action, target = "send_group_msg", {"group_id": int(route.peer)}
    else:
        action, target = "send_private_msg", {"user_id": int(route.peer)}
    try:
        result = await api.call_action(action, self_id=route.login, **target,
                                       message=[{"type": "text", "data": {"text": str(text)}}])
    except Exception:  # noqa: BLE001 - 平台调用失败只记状态，不重放
        return {"state": "failed", "reason": "platform_call_failed"}
    identifier = result.get("message_id") if isinstance(result, Mapping) else None
    return {"state": "delivered", "message_id": identifier,
            "receipt": digest(["text-notice.v1", route.platform_id, route.login, route.peer, str(text)])}


async def send_private_notice(controller, event, *, text, route, transport=None):
    """平台直发一句纯文本；返回有界回执，供诊断与"为什么回了这个人"查证。

    ``route`` 需要 ``platform_id`` / ``login``（self_id）/ ``peer``（对方 user_id）
    与可选的 ``client``；调用方负责把这三样从**已认证的**事件里取出来。
    """
    if not text or not str(text).strip():
        return {"state": "skipped", "reason": "blank_line"}
    api = transport if transport is not None else _transport(controller, route)
    try:
        result = await api.call_action("send_private_msg", self_id=route.login, user_id=int(route.peer),
                                      message=[{"type": "text", "data": {"text": str(text)}}])
    except Exception:  # noqa: BLE001 - 平台调用失败只记状态，不重放
        return {"state": "failed", "reason": "platform_call_failed"}
    identifier = result.get("message_id") if isinstance(result, Mapping) else None
    return {"state": "delivered", "message_id": identifier,
            "receipt": digest(["private-notice.v1", route.platform_id, route.login, route.peer, str(text)])}


def prepare_private_notice_transport(controller, route):
    """Validate the pinned native route before an effectful dispatch barrier."""
    if not isinstance(getattr(route, "peer", None), str) or not route.peer.isdigit():
        raise TaskError("host_notice_route_invalid", "private destination must be a numeric account ID")
    return _transport(controller, route)


def _transport(controller, route):
    """Only the original reverse-WebSocket account of this route may send."""
    client = getattr(route, "client", None)
    api = getattr(getattr(client, "_api", None), "_wsr_api", None)
    clients = getattr(client, "_wsr_api_clients", None)
    if (api is None or type(api) is not controller.native_types.reverse_api
            or clients is None or not clients.get(route.login)):
        raise TaskError("host_notice_transport_changed",
                        "native reverse-WebSocket account is unavailable")
    return api


def private_notice_allowed(settings, *, group=False):
    """正式版：投递不再有"预览/授权"两道闸，因此这句话总是允许发出。

    保留这个函数是为了让"能不能发"只有一个判断点——将来若再加回某种总开关，
    改这里一处即可；调用方不需要知道现在的答案恒为真。
    """
    return True


async def notify_refusal(controller, session, event, *, context):
    """没有对话权限时按配置回一句；返回有界回执或 ``None``（没发就没发）。

    只对**已配置目标**有效：路由要能从已认证的事件里解出来。陌生号没有配置、
    也没有身份，走的是另一条通道（见 docs/PRIVATE_USER_ACCESS_20260930.md）。
    """
    from .recalls import authenticate_notice_route

    if context is None or not private_notice_allowed(controller.settings):
        return None
    application = session.application
    at = controller.now()
    text = application.private_notice.due(context, at)
    if not text:
        return None
    route = authenticate_notice_route(controller, event, ScopeKind.PRIVATE, expected_post="message")
    if route is None:
        return None
    receipt = await send_private_notice(controller, event, text=text, route=route)
    if receipt.get("state") == "delivered":
        application.private_notice.mark_sent(context, context.actor.subject.subject_id, text, at)
    return receipt
