"""Private Reality tools use the received sender, active V2 persona and host Cron."""

from __future__ import annotations

from datetime import datetime, timedelta
import re

from astrbot.core.agent.tool import FunctionTool

from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository


def private_command(event):
    text = str(getattr(event, "message_str", "") or "").strip()
    match = re.fullmatch(r"(?:陪伴\s*)?现实触及(?:\s+(.*))?", text, re.S)
    if match:
        return match.group(1) or "状态"
    compact = re.sub(r"[\s，,。.!！;；:：]+", "", text)
    return "__confirm__" if compact == "我理解风险并确认授权" else None


def private_management_requested(event):
    text = str(getattr(event, "message_str", "") or "")
    return bool(re.search(r"(?:起床|叫醒|现实触及|本机语音|音箱|音响|蓝牙)", text))


async def bound(owner, event, wrapper):
    if not owner.current() or getattr(wrapper.context, "event", None) is not event:
        raise TaskError("reality_private_event_changed", "Reality tool belongs to its original private event")
    contexts = owner.runtime.v2_host_api()._reality_context
    user_id = str(event.get_sender_id())
    original = contexts.target(user_id, umo=str(event.unified_msg_origin))
    await contexts.verified_persona(original, user_id, umo=str(event.unified_msg_origin))
    return contexts, original, user_id


class RealityAudioCommandTool(FunctionTool):
    def __init__(self, owner, event, command):
        super().__init__(name="pc_reality_audio_command",
            description="执行本轮本人发来的现实触及命令或授权确认，内容以收到的原消息为准；返回实际结果。",
            parameters={"type": "object", "properties": {}, "additionalProperties": False})
        self.owner, self.event, self.command = owner, event, command

    async def call(self, context, **kwargs):
        _contexts, _original, user_id = await bound(self.owner, self.event, context)
        cached = self.event.get_extra("companion_v2_reality_audio_command_result")
        if cached is not None:
            return cached
        runtime = self.owner.runtime
        async with runtime._data_lock:
            user = runtime._user(user_id)
            user["umo"] = str(self.event.unified_msg_origin)
            if self.command == "__confirm__":
                reply = runtime.extension_api.apply_pending_confirmation(user_id, str(self.event.message_str))
                reply = reply or "请先发送“陪伴 现实触及 授权”阅读本次设备能力的风险说明，再确认。"
                play = False
            else:
                reply, play = runtime.extension_api.audio_command(user_id, self.command,
                    umo=str(self.event.unified_msg_origin))
            result = encode({"text": reply, "test_scheduled": bool(play)})
            self.event.set_extra("companion_v2_reality_audio_command_result", result)
        if play:
            self.owner.schedule(runtime._test_wakeup_alarm, user)
        return result


class RealityPrivateManagerTool(FunctionTool):
    def __init__(self, owner, event):
        super().__init__(name="pc_reality_private_manage",
            description="管理当前发言者本人的本机语音、叫醒和现实提醒。音频授权只能由本人读说明后确认。"
                        "仅在用户明确要求现实设备触达时创建现实提醒；普通聊天提醒使用原有提醒工具。",
            parameters={"type": "object", "properties": {
                "operation": {"type": "string", "enum": ["status", "request_audio_consent", "revoke_audio_consent",
                    "wakeup", "reminder", "cancel_reminder"]},
                "enabled": {"type": "boolean"}, "time": {"type": "string", "description": "每天叫醒时间 HH:MM"},
                "days": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 6}},
                "topic": {"type": "string"}, "delay_minutes": {"type": "integer", "minimum": 1},
                "scheduled_at": {"type": "string", "description": "一次提醒的 ISO 日期时间"},
                "reminder_id": {"type": "string"},
                "delivery_mode": {"type": "string", "enum": ["audio_only", "audio_and_chat", "chat_on_failure"]}},
                "required": ["operation"], "additionalProperties": False})
        self.owner, self.event = owner, event

    async def call(self, wrapper, **kwargs):
        contexts, original, user_id = await bound(self.owner, self.event, wrapper)
        runtime, application, context = self.owner.runtime, original[1], original[2]
        operation = kwargs.get("operation")
        user = runtime._user(user_id)
        user["umo"] = str(self.event.unified_msg_origin)
        if operation == "status":
            return encode(runtime._reality_touch_user_snapshot(user_id, user))
        if operation in {"request_audio_consent", "revoke_audio_consent"}:
            value = "授权" if operation == "request_audio_consent" else "撤销音频授权"
            reply, _ = runtime.extension_api.audio_command(user_id, value, umo=str(self.event.unified_msg_origin))
            return encode({"text": reply, "confirmation_required": operation == "request_audio_consent"})
        if operation == "cancel_reminder":
            result = await runtime._cancel_reality_touch_official_reminder(user_id,
                reminder_id=str(kwargs.get("reminder_id") or ""), topic=str(kwargs.get("topic") or ""))
            return encode({"cancelled": result})
        if operation == "wakeup" and kwargs.get("enabled") is False:
            reply, _ = runtime.extension_api.audio_command(user_id, "关闭", umo=str(self.event.unified_msg_origin))
            return encode({"saved": True, "text": reply})
        if not runtime._reality_touch_audio_consented(user):
            reply, _ = runtime.extension_api.audio_command(user_id, "授权", umo=str(self.event.unified_msg_origin))
            return encode({"accepted": False, "confirmation_required": True, "prompt": reply})
        if operation == "wakeup":
            alarm = dict(runtime._wakeup_alarm_for_user(user))
            alarm.update(enabled=True, time=str(kwargs.get("time") or alarm.get("time") or ""),
                days=kwargs.get("days", alarm.get("days", list(range(7)))),
                message=str(kwargs.get("topic") or alarm.get("message") or ""),
                delivery_mode=kwargs.get("delivery_mode", alarm.get("delivery_mode", "chat_on_failure")))
            result = runtime._reality_touch_update_alarm(user, alarm)
            runtime._save_data_sync()
            return encode({"saved": True, "alarm": result})
        if operation != "reminder":
            raise ValueError("unsupported private Reality operation")
        topic = str(kwargs.get("topic") or "").strip()
        if not topic or len(topic) > 240:
            raise ValueError("现实提醒需要明确事项")
        if kwargs.get("delay_minutes") is not None:
            delay = kwargs["delay_minutes"]
            if type(delay) is not int or delay <= 0:
                raise ValueError("现实提醒需要未来时间")
            when = runtime._wakeup_now() + timedelta(minutes=delay)
        else:
            when = datetime.fromisoformat(str(kwargs.get("scheduled_at") or ""))
            if when.tzinfo is None:
                when = when.replace(tzinfo=runtime._wakeup_now().tzinfo)
        if when <= runtime._wakeup_now():
            raise ValueError("现实提醒需要未来时间")
        message_id = str(getattr(getattr(self.event, "message_obj", None), "message_id", "") or "")
        if not message_id:
            raise TaskError("reality_event_id_missing", "Reality reminder needs the original received event ID")
        token = digest([context.key, message_id, kwargs])
        operation_ref = OperationRef("reality-reminder-" + token, "reality.reminder.schedule", context.scope,
                                     VersionRef(token, 1), token)
        ledger = OperationRepository(application.runtime)
        receipt = require(ledger.reserve(operation_ref, parameter_hash=digest(kwargs), observed_at=contexts.controller.now()))
        result_key = "reality.reminder.result:" + operation_ref.operation_id
        if receipt.replayed:
            row = application.runtime.read_one("SELECT value FROM runtime_metadata WHERE key=?", (result_key,))
            if receipt.state is OperationState.COMPLETED and row is not None:
                return row["value"]
            return encode({"accepted": False, "reason": "registration_unknown", "replayed": True})
        payload = {"scheduled_ts": int(when.timestamp()), "topic": topic,
                   "request_key": operation_ref.operation_id,
                   "delivery_mode": kwargs.get("delivery_mode", "chat_on_failure")}
        try:
            contexts.recheck(original, user_id, umo=str(self.event.unified_msg_origin))
            accepted = await runtime.extension_api.schedule_reminder(user_id, payload,
                source_text=str(self.event.message_str), trigger_umo=str(self.event.unified_msg_origin))
        except BaseException:
            require(ledger.transition(operation_ref.operation_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.UNKNOWN, observed_at=contexts.controller.now()))
            raise
        created = next((item for item in runtime._reality_touch_reminder_registry(user).values()
                        if item.get("request_key") == operation_ref.operation_id), {})
        result = encode({"accepted": bool(accepted), "reminder_id": created.get("id", ""),
                         "reason": None if accepted else "registration_unknown"})
        with application.runtime.transaction() as connection:
            connection.execute("INSERT INTO runtime_metadata(key,value) VALUES (?,?)", (result_key, result))
            require(ledger.transition(operation_ref.operation_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED if accepted else OperationState.UNKNOWN,
                observed_at=contexts.controller.now()))
        return result
