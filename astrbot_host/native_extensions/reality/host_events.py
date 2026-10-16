"""Camera request guidance using the tools actually offered by V2's core hook."""

from __future__ import annotations

import logging

from astrbot.core.agent.tool import FunctionTool, ToolSet
from companion_v2.execution.models import TaskError

from ..reality_camera import ACTION, explicit_camera_request
from ..request_context import set_turn_context
from .host_tools import RealityAudioCommandTool, RealityPrivateManagerTool, private_command, private_management_requested

logger = logging.getLogger(__name__)


class RealityReminderTool(FunctionTool):
    def __init__(self, owner, event):
        super().__init__(name="pc_reality_touch_reminder",
            description="交付当前 AstrBot Cron 任务中的 V2 现实提醒；按用户设置播放和发送聊天副本，只执行一次。",
            parameters={"type": "object", "properties": {"text": {"type": "string"}},
                        "required": ["text"], "additionalProperties": False})
        self._owner, self._event = owner, event

    async def call(self, context, **kwargs):
        if (not self._owner.current() or getattr(context.context, "event", None) is not self._event
                or not self._owner.reminder(self._event)):
            raise TaskError("reality_reminder_changed", "Reality reminder no longer belongs to this event")
        text = kwargs.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise ValueError("Reality reminder requires bounded final text")
        delivered, detail = await self._owner.runtime._execute_official_reality_touch_reminder(self._event, text)
        return ("提醒已交付：" if delivered else "提醒未交付：") + detail


class RealityHostEvents:
    def __init__(self, runtime, current):
        self.runtime, self.current = runtime, current

    def reminder(self, event):
        metadata = self.runtime._official_reality_touch_metadata(event)
        user = self.runtime.data.get("users", {}).get(metadata.get("user_id")) if metadata else None
        reminder = (user.get("reality_touch_reminders", {}).get(metadata["reminder_id"])
                    if isinstance(user, dict) else None)
        if (not self.runtime._official_reality_touch_matches(reminder, metadata)
                or reminder.get("paused_by_v2")
                or reminder.get("status") not in {"scheduled", "triggered", "delivering",
                                                  "delivered", "completed", "delivery_failed"}):
            return None
        return reminder

    def schedule(self, callback, *args):
        async def run():
            if not self.current():
                return
            try:
                await callback(*args)
            except Exception as error:
                logger.warning("[CompanionV2] 现实提醒后台处理失败 error_type=%s", type(error).__name__)
        self.runtime._create_lifecycle_background_task(run(), label="host-event")

    def request(self, event, req):
        set_turn_context(req, "reality_management")
        set_turn_context(req, "reality_camera")
        metadata = self.runtime._official_reality_touch_metadata(event)
        reminder = self.reminder(event)
        if metadata:
            # A cancelled or duplicate Cron event must not acquire another sending tool.
            executable = reminder is not None and reminder.get("status") in {"scheduled", "triggered"}
            req.func_tool = ToolSet(tools=[RealityReminderTool(self, event)] if executable else [])
            if not executable:
                req.system_prompt = (str(getattr(req, "system_prompt", "") or "")
                    + "\n\n该 V2 现实提醒已取消、已结束或不再有效。结束此任务，不发送消息或播放音频。")
                return
            req.system_prompt = (str(getattr(req, "system_prompt", "") or "")
                + "\n\n这是当前 V2 现实提醒任务。使用原人格自然表达提醒内容，再只调用一次 "
                "pc_reality_touch_reminder(text=最终话语)。专用工具处理音频与聊天副本，"
                "执行后不要再次发送或生成面向用户的副本。若工具不可用则停止，不使用其他发送工具替代。")
            self.schedule(self.runtime._acknowledge_official_reality_touch_trigger, event)
            return
        if not self.runtime._safe_event_is_private(event):
            return
        user_id = str(event.get_sender_id())
        try:
            self.runtime.v2_host_api()._reality_context.target(user_id, umo=str(event.unified_msg_origin))
        except TaskError:
            return
        user = self.runtime._user(user_id, create=False)
        if user is not None:
            self.schedule(self.runtime._maybe_handle_wakeup_feedback, event, user_id, user,
                          str(getattr(event, "message_str", "") or ""))
        command = private_command(event)
        if command is not None or private_management_requested(event):
            tools = list(getattr(getattr(req, "func_tool", None), "tools", ()) or ())
            tool = (RealityAudioCommandTool(self, event, command) if command is not None
                    else RealityPrivateManagerTool(self, event))
            if not any(getattr(item, "name", None) == tool.name for item in tools):
                tools.append(tool)
            req.func_tool = ToolSet(tools=tools)
            set_turn_context(req, "reality_management", "本轮可使用 " + tool.name + " 管理发言者本人的 V2 现实触及。"
                "仅根据本轮明确请求操作；涉及设置或确认时先调用工具，依据实际结果用原人格自然回应。"
                "本人音频授权须先阅读风险说明，再单独发送确认文字；不得替用户确认或虚构成功。"
                "普通回复继续由当前 AstrBot 核心对话完成。")
        if not explicit_camera_request(getattr(event, "message_str", "")):
            return
        tools = getattr(getattr(req, "func_tool", None), "tools", ()) or ()
        camera_tool = next((tool for tool in tools if getattr(tool, "_action", None) == ACTION), None)
        if camera_tool is None:
            return
        set_turn_context(req, "reality_camera", "本轮用户明确请你通过摄像头观察。先使用当前已提供的 " + camera_tool.name
            + "，purpose 准确表达本轮要看什么；拿到实际观察结果后，再用原有人格自然回应。"
            "依据返回的 observation 与 final_response_instruction 表达；"
            "未取得可靠答案时如实说明，不猜测画面或失败原因，也不把不确定说成确定。"
            "不要从时间、姿势或房间物品推断未观察到的情绪、意图或状态。")

    def response(self, event, response):
        if not self.runtime._official_reality_touch_metadata(event):
            return
        reminder = self.reminder(event)
        if getattr(response, "tools_call_name", ()):
            return
        text = str(getattr(response, "completion_text", "") or "").strip()

        async def finish():
            if not reminder.get("tool_called_at") and text:
                await self.runtime._execute_official_reality_touch_reminder(event, text)
            await self.runtime._complete_official_reality_touch_reminder(event)

        # Cron's final completion cannot create a second, ordinary chat send.
        response.completion_text = ""
        response.result_chain = None
        if reminder is not None:
            self.schedule(finish)
