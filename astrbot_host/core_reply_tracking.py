"""Observe AstrBot core group replies without owning generation or delivery."""

from collections import deque
from collections.abc import Mapping
import json
import logging
from threading import Lock

from companion_v2.conversation.group_admission import REASONS
from companion_v2.execution.models import TaskContext
from companion_v2.foundation.refs import ScopeKind
from .core_reply import CORE_REPLY_CONTEXT_EXTRA, is_core_sendable_message


CORE_REPLY_TRACKING_EXTRA = "_companion_v2_core_reply_tracking"
logger = logging.getLogger("astrbot_host.core_reply_tracking")


def _dispatch(state, work):
    """A single background drain preserves this event's storage order."""
    if not callable(state.get("submit")):
        return work()
    with state["_record_lock"]:
        state["_record_queue"].append(work)
        if state["_record_draining"]:
            return None
        state["_record_draining"] = True

    def drain():
        while True:
            with state["_record_lock"]:
                if not state["_record_queue"]:
                    state["_record_draining"] = False
                    return
                pending = state["_record_queue"].popleft()
            try:
                pending()
            except Exception as error:
                logger.warning("[CompanionV2] 核心群回复后台记录暂不可用 error_type=%s",
                               type(error).__name__)

    try:
        state["submit"](drain)
    except Exception as error:
        with state["_record_lock"]:
            state["_record_queue"].clear()
            state["_record_draining"] = False
        logger.warning("[CompanionV2] 核心群回复记录提交暂不可用 error_type=%s", type(error).__name__)
    return None


def _persist(state, stage, *, platform_ids=(), at=None):
    try:
        moment, identifiers = at if at is not None else state["now"](), tuple(platform_ids)
        return _dispatch(state, lambda: state["admission"].mark_core_reply(
            state["context"], state["event_id"], stage=stage, at=moment, platform_ids=identifiers))
    except Exception as error:
        logger.warning("[CompanionV2] 核心群回复记录暂不可用 stage=%s error_type=%s",
                       stage, type(error).__name__)
        return None


def _log(state, stage):
    if state["mentioned"] or stage in state["logged_stages"]:
        return
    state["logged_stages"].add(stage)
    send_state = state["send_state"]
    decision = dict(state.get("participation") or {})
    laya = dict(state.get("laya") or {})
    laya_action = (laya.get("applied_decision") or {}).get("action", "not_applied")

    def record():
        try:
            if not state["admission"].mark_core_reply_logged(state["context"], state["event_id"], stage):
                return
        except Exception:
            return
        reason = decision.get("reason") or ("Laya 分类为 " + laya_action if laya_action != "not_applied"
                 else REASONS.get(state["reason"], state["reason"]))
        source = decision.get("source", "model") if decision.get("reason") else "laya" if laya_action != "not_applied" else "policy"
        logger.info("[CompanionV2] 非@群回复原因 event_ref=%s stage=%s trigger=%s reason=%s "
                    "reason_source=%s participation=%s laya_status=%s laya_action=%s send_state=%s platform_confirmed=false",
                    state["event_id"], stage, state["reason"],
                    json.dumps(reason, ensure_ascii=False), source, decision.get("mode", "pending"),
                    laya.get("status", "unavailable"), laya_action, send_state)

    _dispatch(state, record)


def _platform_ids(result):
    """Use only IDs actually returned by the send call, never event/input IDs."""
    if isinstance(result, Mapping):
        identifier = result.get("message_id")
        if identifier is None and isinstance(result.get("data"), Mapping):
            identifier = result["data"].get("message_id")
    else:
        identifier = getattr(result, "message_id", None)
    return (str(identifier),) if type(identifier) in (int, str) and str(identifier) else ()


def _is_core_delivery(event, state, *, streaming=False):
    core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    if (not state["inflight"] or not isinstance(core, dict)
            or core.get("group_participation", {}).get("mode") == "skip"):
        return False
    getter = getattr(event, "get_result", None)
    try:
        result = getter() if callable(getter) else None
        name = getattr(getattr(result, "result_content_type", None), "name", "")
        if streaming and name == "STREAMING_RESULT":
            return True
        if not core.get("delivery_guard_active"):
            return False
        if not callable(getter):
            return True
        if name in ("LLM_RESULT", "STREAMING_RESULT"):
            return True
        is_llm_result = getattr(result, "is_llm_result", None)
        return bool(is_llm_result()) if callable(is_llm_result) else False
    except Exception:
        return False


def prepare_core_reply_tracking(event, prepared, *, admission, now, reason="", mentioned=False, submit=None):
    """Attach after the authorization wrapper; bookkeeping never blocks a reply."""
    if not isinstance(prepared, Mapping):
        return None
    context, event_id = prepared.get("context"), prepared.get("event_id")
    if (not isinstance(context, TaskContext) or context.scope.kind is not ScopeKind.GROUP
            or not isinstance(event_id, str) or not event_id):
        return None
    state = event.get_extra(CORE_REPLY_TRACKING_EXTRA)
    if not isinstance(state, dict):
        state = {"context": context, "event_id": event_id, "admission": admission, "now": now,
                 "laya": dict(prepared.get("laya_decision") or {}),
                 "reason": reason, "mentioned": bool(mentioned), "inflight": False,
                 "send_state": "not_started", "send_attempts": 0, "send_returns": 0,
                 "unknown_sends": 0, "send_failed": 0, "completed": False,
                 "streaming_depth": 0, "logged_stages": set(), "submit": submit,
                 "_record_queue": deque(), "_record_lock": Lock(), "_record_draining": False}
        state["_original_send"] = event.send
        state["_original_streaming"] = getattr(event, "send_streaming", None)

        def begin_send(*, at=None):
            state["completed"] = False
            state["send_attempts"] += 1
            if state["send_state"] not in ("unknown", "denied"):
                state["send_state"] = "started"
            _persist(state, "send_started", at=at)

        def send_returned(result):
            state["send_returns"] += 1
            if state["send_state"] not in ("unknown", "denied"):
                state["send_state"] = "returned"
            _persist(state, "send_returned", platform_ids=_platform_ids(result))

        def send_failed():
            core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
            denied = isinstance(core, dict) and core.get("denial_notified")
            state["send_state"] = "denied" if denied else "unknown"
            if not denied:
                state["unknown_sends"] += 1
            _persist(state, "send_denied" if denied else "send_unknown")

        async def observed_call(original, args, kwargs):
            message = args[0] if args else kwargs.get("message")
            if not _is_core_delivery(event, state):
                return await original(*args, **kwargs)
            from .core_reply_presentation import present_core_reply_message
            presented = present_core_reply_message(event, message, from_stream=True)
            if presented is None:
                return None
            if presented is not message:
                if args:
                    args = (presented, *args[1:])
                else:
                    kwargs = {**kwargs, "message": presented}
            if not is_core_sendable_message(presented):
                return await original(*args, **kwargs)
            # after_message_sent closes one delivery phase. Tool loops can later
            # yield another real reply on this same event.
            stream = state.get("_stream_observation")
            if state["streaming_depth"] and isinstance(stream, dict):
                stream["nested"] += 1
            begin_send()
            try:
                result = await original(*args, **kwargs)
            except BaseException:
                send_failed()
                raise
            send_returned(result)
            return result

        async def observed_send(*args, **kwargs):
            return await observed_call(state["_original_send"], args, kwargs)

        async def observed_streaming(*args, **kwargs):
            if state["streaming_depth"] or not _is_core_delivery(event, state, streaming=True):
                return await state["_original_streaming"](*args, **kwargs)
            observed = {"nested": 0, "started_at": None}
            core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
            attempts_before = core.get("send_attempts", 0) if isinstance(core, dict) else 0
            original_args, original_kwargs = list(args), dict(kwargs)
            generator = original_args[0] if original_args else original_kwargs.get("generator")
            if generator is not None and hasattr(generator, "__aiter__"):
                async def observed_chunks():
                    async for chunk in generator:
                        if observed["started_at"] is None and is_core_sendable_message(chunk):
                            observed["started_at"] = state["now"]()
                        yield chunk
                if original_args:
                    original_args[0] = observed_chunks()
                else:
                    original_kwargs["generator"] = observed_chunks()
            elif is_core_sendable_message(generator):
                observed["started_at"] = state["now"]()
            state["_stream_observation"] = observed
            state["streaming_depth"] += 1
            try:
                result = await state["_original_streaming"](*original_args, **original_kwargs)
            except BaseException:
                core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
                parts_only = isinstance(core, dict) and core.get("_stream_send_accounted_by_parts")
                attempted = (not isinstance(core, dict) or "_send_wrapper" not in core
                             or core.get("send_attempts", 0) > attempts_before)
                if not observed["nested"] and not parts_only:
                    if observed["started_at"] is not None and attempted:
                        begin_send(at=observed["started_at"])
                        send_failed()
                    else:
                        core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
                        if isinstance(core, dict) and core.get("denial_notified"):
                            state["send_state"] = "denied"
                            _persist(state, "send_denied")
                raise
            else:
                core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
                parts_only = isinstance(core, dict) and core.get("_stream_send_accounted_by_parts")
                attempted = (not isinstance(core, dict) or "_send_wrapper" not in core
                             or core.get("send_attempts", 0) > attempts_before)
                if not observed["nested"] and observed["started_at"] is not None and not parts_only and attempted:
                    begin_send(at=observed["started_at"])
                    send_returned(result)
                return result
            finally:
                state["streaming_depth"] -= 1
                state.pop("_stream_observation", None)
                # AstrBot returns before after_message_sent on streaming replies.
                finish_core_reply_tracking(event)

        state["_send_wrapper"] = observed_send
        state["_streaming_wrapper"] = observed_streaming
        event.set_extra(CORE_REPLY_TRACKING_EXTRA, state)
    elif state["event_id"] != event_id or state["context"] != context:
        return None
    try:
        note_live = getattr(admission, "note_live_core_turn", None)
        if callable(note_live):
            note_live(context, event_id, active=True)
        at, instruction = now(), prepared.get("instruction", "")
        _dispatch(state, lambda: admission.record_core_reply(context, event_id, instruction=instruction,
            reason=reason, mentioned=mentioned, at=at,
            continuation=(prepared.get("group_admission") or {}).get("continuation")))
    except Exception as error:
        logger.warning("[CompanionV2] 核心群回复准入记录暂不可用 error_type=%s", type(error).__name__)
    event.send = state["_send_wrapper"]
    if callable(state["_original_streaming"]):
        event.send_streaming = state["_streaming_wrapper"]
    _log(state, "admitted")
    return state


def mark_core_reply_inflight(event):
    state = event.get_extra(CORE_REPLY_TRACKING_EXTRA)
    if not isinstance(state, dict) or state["completed"]:
        return None
    if not state["inflight"]:
        state["inflight"] = True
        _persist(state, "inflight")
    return state


def activate_core_reply_tracking(event):
    """Re-arm the optional observer after the core guard re-arms each result."""
    state = event.get_extra(CORE_REPLY_TRACKING_EXTRA)
    if not isinstance(state, dict):
        return
    event.send = state["_send_wrapper"]
    if callable(state["_original_streaming"]):
        event.send_streaming = state["_streaming_wrapper"]


def observe_core_reply_tool_delivery(event, stage, result=None):
    """Observe a native tool's direct context send without sending through event."""
    try:
        state = event.get_extra(CORE_REPLY_TRACKING_EXTRA)
        if not isinstance(state, dict):
            return None
        if stage == "started":
            state["inflight"] = True
            state["completed"] = False
            state["send_attempts"] += 1
            if state["send_state"] not in ("unknown", "denied"):
                state["send_state"] = "started"
            _persist(state, "send_started")
            return None
        if stage == "returned":
            state["send_returns"] += 1
            if state["send_state"] not in ("unknown", "denied"):
                state["send_state"] = "returned"
            _persist(state, "send_returned", platform_ids=_platform_ids(result))
        elif stage == "unknown":
            state["unknown_sends"] += 1
            state["send_state"] = "unknown"
            _persist(state, "send_unknown")
        elif stage == "denied":
            state["send_state"] = "denied"
            _persist(state, "send_denied")
        elif stage == "failed":
            state["send_failed"] += 1
            if state["send_state"] not in ("unknown", "denied"):
                state["send_state"] = "failed"
            _persist(state, "send_failed")
        else:
            return None
        return finish_core_reply_tracking(event)
    except Exception as error:
        logger.warning("[CompanionV2] 核心工具发送记录暂不可用 stage=%s error_type=%s",
                       stage, type(error).__name__)
        return None


def observe_core_group_participation(event, decision):
    """Queue the role's native choice on the same FIFO as send observations."""
    state = event.get_extra(CORE_REPLY_TRACKING_EXTRA)
    if isinstance(state, dict):
        state["participation"] = dict(decision)
        frozen = dict(decision)
        origin = {key: frozen[key] for key in ("source", "decision_action") if frozen.get(key)}
        _dispatch(state, lambda: state["admission"].mark_core_participation(
            state["context"], state["event_id"], mode=frozen["mode"], reason=frozen["reason"],
            act=frozen["act"], signature=frozen["signature"], **origin))


def finish_core_reply_tracking(event, *, log_completion=True):
    """Close the phase using observed send outcomes, not _has_send_oper."""
    state = event.get_extra(CORE_REPLY_TRACKING_EXTRA)
    if not isinstance(state, dict):
        return None
    if not state["completed"]:
        state["completed"] = True
        try:
            note_live = getattr(state.get("admission"), "note_live_core_turn", None)
            if callable(note_live):
                note_live(state["context"], state["event_id"], active=False)
        except Exception:
            pass
        _persist(state, "completed")
    if log_completion:
        _log(state, "completed")
    return {key: state[key] for key in ("event_id", "send_state", "send_attempts", "send_returns", "unknown_sends", "send_failed")}
