"""Chat-side '全部重置' for one private relationship, outside the model.

V1 的「全部重置 / 重置插件」在 V2 没有聚合服务。这里把它收窄成两件可核对的事：
重置当前私聊的会话窗口、把该关系的记忆事实标记为遗忘；人格、模型与连接配置、
日历、关系资料不动，平台消息与日志也不物理删除。

必须在模型之前执行并平台直发回执：确认消息所属的批次会被窗口重置一并取消，
若走模型回复，回执可能永远发不出去。因此先用 `prepare_core_reply_context`
只做路由与身份解析（不建批次），确认后再执行。
"""

from __future__ import annotations

from companion_v2.conversation.reset import ConversationWindow
from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind
from companion_v2.memory.management import MemoryManagement

from .binding import message_text
from .command_authority import is_core_subject
from .functional_commands import confirmation_code, parse_functional_command
from .private_notice import send_private_notice
from .recalls import authenticate_notice_route


def parse_reset_command(text):
    command = parse_functional_command(text, channel="private")
    return command if command is not None and command.intent == "reset_all" else None


def reset_confirmation_code(window, token):
    return digest(["reset-all-confirm.v1", window.key, token])[:6].upper()


def _preview_text(counts):
    total = counts["active"] + counts["already_inactive"]
    return (f"尚未执行：全部重置会重置当前私聊的会话窗口，并把 {total} 条记忆事实标记为遗忘"
            f"（其中活跃 {counts['active']} 条）。人格、模型与连接配置、日历、关系资料不会改动；"
            "平台消息、日志和备份不会被物理删除。")


def _failure_reason(failure, fallback="程序没有完成该操作"):
    return failure.reason or fallback


async def receive_reset_command(controller, event, *, target=None):
    """Return None when this is not the handled private reset command."""
    command = parse_reset_command(message_text(event))
    if command is None:
        return None
    prepare = getattr(controller, "prepare_core_reply_context", None)
    if not callable(prepare) or controller.session is None:
        return None
    route = None
    try:
        route = authenticate_notice_route(controller, event, ScopeKind.PRIVATE, expected_post="message")
        if route is None:
            return None
        plan = await prepare(event, target)
        if plan.failure is not None:
            return None
        context = plan.unwrap().context
        session = controller.session
        if context.scope.kind is not ScopeKind.PRIVATE:
            return None
        if not is_core_subject(session.runtime, context.actor.subject):
            text = "未执行：全部重置只允许安装核心管理员执行。"
        else:
            text = _decide(command, context, session)
    except TaskError as error:
        if route is None:
            return None
        text = f"未执行：全部重置没有完成（{error.code}）。"
    receipt = await send_private_notice(controller, event, text=text, route=route)
    if receipt.get("state") != "delivered":
        return Outcome.failed("reset_command_reply_not_sent",
                              "the reset receipt could not be delivered")
    return Outcome.success({"handled": True, "text": text})


def _decide(command, context, session):
    application = session.application
    window = ConversationWindow.from_scope(context.scope)
    management = MemoryManagement(application.memory, None)
    preview = management.preview_clear(context)
    if preview.failure is not None:
        return f"未执行：读取记忆预览失败（{_failure_reason(preview.failure)}）。"
    value = preview.unwrap()
    counts, token = value["counts"], value["revision_token"]
    code = reset_confirmation_code(window, token)
    supplied = confirmation_code(command.argument)
    if not supplied:
        return _preview_text(counts) + f"确认请回复「陪伴 全部重置 确认 {code}」。"
    if supplied != code:
        return "未执行：确认码不匹配或记忆内容已变化。请重新发送「陪伴 全部重置」获取新的确认码。"

    reset_id = "chat-reset-" + digest([window.key, token])
    reset = application.reset_conversation_window(window, reset_id=reset_id)
    if reset.failure is not None:
        return f"未执行：会话窗口重置失败（{_failure_reason(reset.failure)}），记忆没有清理。"
    batches = len(reset.unwrap().get("batches") or ())
    cleared = management.clear(context, expected_revision_token=token,
                               operation_key="chat-reset-" + digest([window.key, token]))
    if cleared.failure is not None:
        return (f"部分完成：会话窗口已重置（取消 {batches} 个批次），"
                f"但记忆清理未完成（{_failure_reason(cleared.failure)}）。")
    return (f"已执行：重置会话窗口（取消 {batches} 个批次），"
            f"{cleared.unwrap()['forgotten_count']} 条记忆事实标记为遗忘。"
            "人格、模型与连接配置、日历和关系资料未改动，平台消息与日志未物理删除。")
