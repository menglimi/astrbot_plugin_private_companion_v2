"""Handle authenticated OneBot poke notices on their original native route."""

from collections.abc import Mapping

from companion_v2.adapters.astrbot.native import account_number
from companion_v2.conversation.quotes.models import message_number
from companion_v2.execution.models import TaskError, digest, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind
from companion_v2.storage.repositories import InboxRepository

from .recalls import authenticate_notice_route, is_notice_event


CONSUMER = "conversation.native_poke.v1"


def is_poke_notice(event):
    raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
    return (is_notice_event(event) and raw.get("notice_type") == "notify"
            and raw.get("sub_type") == "poke")


def capture_poke(controller, event):
    if not is_poke_notice(event):
        return None
    raw = event.message_obj.raw_message
    kind = ScopeKind.GROUP if raw.get("group_id") is not None else ScopeKind.PRIVATE
    route = authenticate_notice_route(controller, event, kind)
    if route is None:
        return None
    if account_number(raw.get("target_id")) != route.login or route.sender == route.login:
        return None
    happened_at = raw.get("time")
    if type(happened_at) is not int or happened_at <= 0:
        raise TaskError("host_poke_invalid", "poke notice has no stable native event time")
    return route, happened_at


async def _authorize(controller, route):
    session, settings = controller.session, controller.settings
    if hasattr(settings, "targets"):
        targets = settings.group_targets if route.kind is ScopeKind.GROUP else settings.targets
        target = (settings.group_target(route.platform_id, route.login, route.peer)
                  if route.kind is ScopeKind.GROUP
                  else settings.private_target(route.platform_id, route.login, route.peer))
        if target is None:
            raise TaskError("host_poke_route_changed", "poke target is no longer configured")
        if route.kind is ScopeKind.GROUP:
            # 正式版没有"预览/群投递授权"这两道闸：目标认得出来就能回。
            controller.authority.group_delivery.access(target)
            account = session.bridge.groups.accounts[(route.platform_id, route.login)]
            await session.bridge.groups._role(account, route.session_id)
        else:
            context, _ = await session.synchronize(target)
            session.authorize(context)
    else:
        session.require_delivery_authorization()
        require(session.application.tasks.check_context_access(
            session.profile.target, action="conversation.reply", observed_at=controller.now()))
        await session.bridge.verify_role(session.profile.target.scope, session.profile.target.role_binding)


def _transport(controller, route):
    client = route.client
    api = client._api._wsr_api
    if (type(api) is not controller.native_types.reverse_api or api._api_clients is not client._wsr_api_clients
            or not client._wsr_api_clients.get(route.login)):
        raise TaskError("host_poke_transport_changed", "native reverse-WebSocket account is unavailable")
    return api


async def _dispatch_guard(controller, event, captured):
    route, _ = captured
    await _authorize(controller, route)
    if capture_poke(controller, event) != captured:
        raise TaskError("host_poke_route_changed", "poke native route changed before dispatch")
    return _transport(controller, route)


async def receive_poke(controller, event):
    if not is_poke_notice(event) or not controller.poke_policy.enabled:
        return None
    async with controller._control_lock:
        try:
            captured = capture_poke(controller, event)
            if captured is None:
                return None
            route, happened_at = captured
            key = digest([controller.session.runtime.installation_id, route.platform_id, route.login,
                          route.kind.value, route.peer, route.sender, happened_at])
            receipt = require(InboxRepository(controller.session.runtime).accept(
                consumer=CONSUMER, event_id=key, payload_hash=digest([route.kind.value, route.peer,
                    route.sender, route.login, happened_at]), observed_at=controller.now()))
            if receipt.replayed:
                return Outcome.success({"state": "replayed", "replayed": True})
            reply = controller.poke_policy.reply_for(key)
            if reply is None:
                return Outcome.success({"state": "skipped", "replayed": False})
            api = await _dispatch_guard(controller, event, captured)
            action = "send_group_msg" if route.kind is ScopeKind.GROUP else "send_private_msg"
            target = {"group_id" if route.kind is ScopeKind.GROUP else "user_id": int(route.peer)}
            try:
                result = await api.call_action(action, self_id=route.login, **target,
                    message=[{"type": "text", "data": {"text": reply}}])
            except Exception:
                return Outcome.success({"state": "unknown", "replayed": False, "poke_back": False})
            identifier = result.get("message_id") if isinstance(result, Mapping) else None
            try:
                message_id = message_number(identifier, error_code="host_poke_ack_invalid")
            except TaskError:
                return Outcome.success({"state": "unknown", "replayed": False, "poke_back": False})
            if not controller.poke_policy.poke_back(key):
                return Outcome.success({"state": "delivered", "replayed": False, "poke_back": False,
                                        "message_id": message_id})
            try:
                api = await _dispatch_guard(controller, event, captured)
            except (TaskError, ValueError, TypeError, AttributeError, KeyError):
                return Outcome.success({"state": "delivered", "replayed": False, "poke_back": False,
                                        "message_id": message_id})
            try:
                await api.call_action("group_poke" if route.kind is ScopeKind.GROUP else "friend_poke",
                    self_id=route.login, **({"group_id": int(route.peer)} if route.kind is ScopeKind.GROUP else {}),
                    user_id=int(route.sender))
            except Exception:
                return Outcome.success({"state": "delivered", "replayed": False, "poke_back": "unknown",
                                        "message_id": message_id})
            return Outcome.success({"state": "delivered", "replayed": False, "poke_back": True,
                                    "message_id": message_id})
        except TaskError as error:
            return Outcome.failed(error.code, str(error))
        except (ValueError, TypeError, AttributeError, KeyError, StopIteration):
            return Outcome.failed("host_poke_invalid", "native poke notice could not be authenticated")
