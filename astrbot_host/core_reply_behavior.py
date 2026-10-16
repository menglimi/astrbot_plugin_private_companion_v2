"""Native main-chain social learning and genuine group mention delivery."""

from threading import Lock
from collections import deque
import logging

from astrbot.core.message.components import At

from companion_v2.conversation.behavior.service import FEEDBACK, LEARN, PLAN
from companion_v2.execution.models import TaskError
from .core_reply import CORE_REPLY_CONTEXT_EXTRA, sent_core_text


logger = logging.getLogger(__name__)


def execute_core_behavior(session, action, arguments, call_id):
    owner = session.application.tools.group_participation.behavior
    original = session.prepared["native_input"]
    frame = owner.frame(session.context, original)
    at = session.application.tasks.now()
    if action == LEARN:
        payload = owner.learn(session.context, frame, arguments, at=at)
    elif action == FEEDBACK:
        payload = owner.feedback(session.context, frame, arguments, at=at)
    elif action == PLAN:
        if session.state.get("send_attempts", 0):
            raise TaskError("group_behavior_reply_started", "select the interaction before the first send")
        admission = session.prepared.get("group_admission") or {}
        if not admission.get("mentioned") and session.state.get("group_participation", {}).get("mode") != "reply":
            raise TaskError("group_behavior_participation_required", "choose whether to participate before planning an interaction")
        payload = owner.plan(session.context, frame, arguments, turn_id=session.turn_id, call_id=call_id, at=at)
        session.state["_behavior_plan"] = payload
        session.state["_behavior_owner"] = owner
        session.state["_behavior_now"] = session.application.tasks.now
        payload = {"attempt_id": payload["attempt_id"], "habit_id": payload["habit_id"],
                   "target_id": payload["target_id"], "state": "prepared_for_this_reply", "sent": False,
                   "instruction": "继续生成自然的互动文字；系统只在本轮首个文字段添加真实 @，不会代替你发送。"}
    else:
        raise TaskError("core_tool_unavailable", "unknown behavior operation")
    return {"state": "succeeded", "effect": "none", "payload": payload}


def behavior_targets(event, prepared, *, first_text, text):
    core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    if (not isinstance(core, dict) or core.get("prepared") is not prepared
            or prepared.get("channel") != "group" or not text.strip()):
        return ()
    plan, owner = core.get("_behavior_plan"), core.get("_behavior_owner")
    if not plan or owner is None or core.get("group_participation", {}).get("mode") == "skip":
        return ()
    owner.validate_plan(prepared["context"], plan)
    return (plan["target_id"],) if first_text else ()


def observe_core_behavior_delivery(event, message, stage):
    """Book only the actual decorated wire part, after the existing send guard."""
    core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    plan = core.get("_behavior_plan") if isinstance(core, dict) else None
    if not plan or stage not in ("started", "returned", "unknown", "failed"):
        return
    if not any(isinstance(part, At) and str(part.qq) == plan["target_id"] for part in getattr(message, "chain", ())):
        return
    owner = core.get("_behavior_owner")
    if owner is None:
        return
    at, text = core["_behavior_now"](), sent_core_text(message)
    from .core_reply_tracking import _dispatch
    queue = core.setdefault("_behavior_records", {"submit": core.get("media_submit"),
        "_record_lock": Lock(), "_record_queue": deque(), "_record_draining": False})
    try:
        _dispatch(queue, lambda: owner.delivery(core["prepared"]["context"], plan["attempt_id"],
                                               stage=stage, text=text, at=at))
    except Exception as error:
        logger.warning("[CompanionV2] 互动回执记录暂不可用 stage=%s error_type=%s", stage, type(error).__name__)
