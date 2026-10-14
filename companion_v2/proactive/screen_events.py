"""Bounded proactive sharing of explicitly captured, currently authorized Screen results."""

import asyncio
from datetime import datetime, time, timedelta, timezone
import json
from zoneinfo import ZoneInfo

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import ScopeKind, SourceRef, VersionRef
from companion_v2.screen.models import ScreenFeedbackKind
from companion_v2.screen.peek import KIND as PEEK_KIND
from companion_v2.screen.repositories import ScreenRepository
from companion_v2.sources.dependencies import link
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord

from .contact_models import ContactIntent
from .diagnostic_models import DiagnosticSourceError
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


SOURCE_OWNER = "proactive.screen"
MAX_AGE = timedelta(hours=24)
PAGE_SIZE = 32
# T20: the two autonomous peek episodes V1 scheduled from its own loop. A goodnight
# check follows one delivered goodnight line; a follow-up peek follows a delivered
# proactive message that stayed unanswered.
GOODNIGHT_WORDS = ("晚安", "好梦", "早点睡", "睡吧", "休息吧", "明天见")
# V1 only attempted to schedule this check while it was handling an outbound reply,
# so it bounded the episode at 30 minutes. This scheduler ticks on its own, and the
# configured delay (up to 180 minutes) has to fit inside the bound.
GOODNIGHT_MAX_AGE = timedelta(hours=6)
GOODNIGHT_PREFIX = "screen-peek-goodnight:"
FOLLOWUP_PREFIX = "screen-peek-followup:"


class ScreenContactEvents:
    def __init__(self, contacts):
        self.contacts, self.runtime = contacts, contacts.runtime
        self.tasks = contacts.tasks
        self.screens = ScreenRepository(self.runtime, authorizer=self.tasks.identity)
        self.guard = bind(self.runtime, SOURCE_OWNER, self._validate_source)

    def close(self):
        self.guard.close()

    def _latest_contact(self, context):
        return self.runtime.read_one("""SELECT MAX(created_at) AS latest FROM proactive_contacts
            WHERE origin_key = ? AND json_extract(record_json, '$.purpose') = 'screen'""", (context.key,))

    def _daily_count(self, context, preferences, at):
        zone = ZoneInfo(preferences.values["quiet_timezone"])
        local_day = at.astimezone(zone).date()
        start = datetime.combine(local_day, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(local_day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        return self.runtime.read_one("""SELECT COUNT(*) FROM proactive_contacts
            WHERE origin_key = ? AND json_extract(record_json, '$.purpose') = 'screen'
              AND created_at >= ? AND created_at < ?""", (context.key, stamp(start), stamp(end)))[0]

    def _cooling_down(self, context, preferences, at):
        latest = self._latest_contact(context)
        minutes = preferences.values["screen_glance_cooldown_minutes"]
        return bool(latest and latest["latest"] and at < datetime.fromisoformat(latest["latest"])
                    + timedelta(minutes=minutes))

    def _material(self, context, feedback_id, capture_id, at):
        reference = require(self.screens.published_reference(capture_id, scope=context.scope))
        result = require(self.screens.read_feedback(feedback_id, capture=reference,
            resolved=context.actor, observed_at=at))
        if result.anchor.kind is not ScreenFeedbackKind.PROACTIVE or result.analysis is None:
            raise TaskError("contact_screen_feedback_unavailable", "Screen result is not an authorized proactive analysis")
        text = result.analysis.interpretation.strip()
        if not text:
            raise TaskError("contact_screen_interpretation_unavailable", "Screen analysis has no shareable interpretation")
        return reference, result, text[:4096]

    def _reference(self, context, feedback_id, analysis):
        identifier = "contact-screen-source-" + digest([context.key, feedback_id, analysis.version])
        return SourceRef(identifier, SOURCE_OWNER, context.scope, VersionRef(identifier, 1), analysis.created_at)

    def _project(self, context, feedback_id, capture_id, at):
        reference, result, text = self._material(context, feedback_id, capture_id, at)
        analysis = result.analysis
        source = self._reference(context, feedback_id, analysis)
        body = {"event": "authorized_screen_observation", "observed_at": stamp(analysis.created_at),
                "interpretation": text,
                "meaning": "这是已授权 Screen 对当时可见画面的模型解读，不是屏幕原文、用户经历或当前画面；只分享明确可见且仍相关的内容。"}
        receipt = {"context": json.loads(encode(context)), "feedback_id": feedback_id,
                   "capture_id": capture_id, "analysis_hash": digest(analysis)}
        payload = json.dumps({**body, "_receipt": receipt}, ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"))
        with self.runtime.transaction():
            require(self.contacts.sources.publish(SourceRecord(source, context.audience, digest(payload), payload),
                                                   observed_at=at))
            link(self.runtime, source, (reference.source,), at)
        opportunity = self._opportunity(context, feedback_id, analysis.created_at, reference)
        marker = {"feedback_id": feedback_id, "capture_id": capture_id,
                  "analysis_hash": digest(analysis), "expires_at": stamp(opportunity.expires_at),
                  "source": json.loads(encode(source))}
        thought = Thought("screen-thought-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
            "有一条来自之前明确授权识屏的观察。判断现在是否仍适合自然提起；不要说成正在看屏幕，也可以跳过。",
            EvidenceSnapshot(context.scope, at, (source,)), 1.0)
        return opportunity, (ContactIntent("screen", thought),), marker

    @staticmethod
    def _opportunity(context, feedback_id, created_at, reference):
        expires = min(created_at + MAX_AGE, reference.source.expires_at or created_at + MAX_AGE)
        return Opportunity("screen-" + digest([context.key, feedback_id]), context.scope, created_at, expires)

    def peek_due(self, context, preferences, at):
        """Decide one autonomous peek for this window; never a second one for an episode.

        The caller has already confirmed that the Screen extension is registered and
        that the window allows an interpreted capture. Everything here only decides
        *when*: a delivered goodnight line after its delay, or a delivered proactive
        message that stayed unanswered.
        """
        if (context.scope.kind is not ScopeKind.PRIVATE or not preferences.values["automatic_enabled"]
                or not preferences.values["screen_glance_enabled"] or preferences.reason("screen")):
            return None
        decision = self._goodnight_peek(context, preferences, at)
        if decision is None:
            decision = self._followup_peek(context, preferences, at)
        return decision

    def _attempts_today(self, context, preferences, at):
        zone = ZoneInfo(preferences.values["quiet_timezone"])
        day = at.astimezone(zone).date()
        start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        row = self.runtime.read_one("""SELECT COUNT(*) FROM execution_tasks
            WHERE origin_key = ? AND kind = ? AND created_at >= ? AND created_at < ?""",
            (context.key, PEEK_KIND, stamp(start), stamp(end)))
        return row[0]

    def _attempted(self, task_id):
        return self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,)) is not None

    def _latest_attempt(self, context, prefix):
        row = self.runtime.read_one("""SELECT MAX(created_at) AS latest FROM execution_tasks
            WHERE origin_key = ? AND task_id LIKE ?""", (context.key, prefix + "%"))
        return datetime.fromisoformat(row["latest"]) if row is not None and row["latest"] else None

    def _user_spoke_after(self, context, moment):
        if self.contacts.history is not None:
            latest = self.contacts.history.interaction(context, self.contacts.tasks.now(), action="proactive.contact")
            if latest.get("last_input_at") is not None and datetime.fromisoformat(latest["last_input_at"]) > moment:
                return True
        row = self.runtime.read_one("""SELECT MAX(b.created_at) AS latest FROM conversation_inputs i
            JOIN conversation_batches b ON b.batch_id = i.batch_id
            JOIN conversation_flows f ON f.batch_id = b.batch_id
            WHERE f.route_key = ? AND i.withdrawn = 0""", (context.scope.key,))
        return row is not None and row["latest"] is not None and datetime.fromisoformat(row["latest"]) > moment

    def _goodnight_peek(self, context, preferences, at):
        if not preferences.values["screen_glance_goodnight_enabled"]:
            return None
        delay = timedelta(minutes=preferences.values["screen_glance_goodnight_delay_minutes"])
        rows = self.runtime.read_all("""SELECT p.part_id, p.text, p.delivered_at
            FROM conversation_parts p JOIN conversation_batches b ON b.batch_id = p.batch_id
            JOIN conversation_flows f ON f.batch_id = b.batch_id
            WHERE f.route_key = ? AND p.state = 'delivered' AND p.delivered_at IS NOT NULL
            ORDER BY p.delivered_at DESC, p.sequence DESC LIMIT 8""", (context.scope.key,))
        history = self.contacts.history
        if history is not None and history.messages is not None:
            from companion_v2.conversation.native_history import body, reference, rows as native_rows
            native = []
            for observed in native_rows(self.runtime, context, end=stamp(at), kind="assistant", limit=8):
                try:
                    item = body(history.messages, reference(observed), context, at)
                except TaskError:
                    continue
                native.append({"part_id": observed["observation_id"], "text": item["text"], "delivered_at": item["delivered_at"]})
            rows = sorted((*rows, *native), key=lambda row: row["delivered_at"], reverse=True)[:8]
        for row in rows:
            delivered = datetime.fromisoformat(row["delivered_at"])
            if delivered > at or at - delivered > GOODNIGHT_MAX_AGE:
                continue
            if not any(word in (row["text"] or "") for word in GOODNIGHT_WORDS):
                continue
            if at < delivered + delay:
                return None
            if self._user_spoke_after(context, delivered):
                return None
            task_id = GOODNIGHT_PREFIX + digest([context.key, row["part_id"]])
            if self._attempted(task_id) or self._cooling_down(context, preferences, at):
                return None
            # V1 counted a goodnight check against the shared daily quota.
            if self._attempts_today(context, preferences, at) >= preferences.values["screen_glance_daily_limit"]:
                return None
            return {"purpose": "goodnight", "episode_at": delivered, "task_id": task_id}
        return None

    def _followup_peek(self, context, preferences, at):
        if not preferences.values["screen_glance_followup_enabled"]:
            return None
        after = timedelta(minutes=preferences.values["screen_glance_followup_after_minutes"])
        cooldown = timedelta(minutes=preferences.values["screen_glance_followup_cooldown_minutes"])
        row = self.runtime.read_one("""SELECT c.contact_id, d.delivered_at,
                json_extract(c.record_json, '$.purpose') AS purpose
            FROM proactive_contacts c JOIN background_deliveries d
                ON d.task_id = c.task_id AND d.state = 'delivered'
            WHERE c.origin_key = ? AND d.delivered_at IS NOT NULL
            ORDER BY d.delivered_at DESC LIMIT 1""", (context.key,))
        if row is None or row["purpose"] == "screen":
            return None
        delivered = datetime.fromisoformat(row["delivered_at"])
        if at < delivered + after or self._user_spoke_after(context, delivered):
            return None
        previous = self._latest_attempt(context, FOLLOWUP_PREFIX)
        if previous is not None and at < previous + cooldown:
            return None
        if self._cooling_down(context, preferences, at):
            return None
        # V1 exempted this chain from the daily count but kept every cooldown.
        return {"purpose": "followup", "episode_at": delivered,
                "task_id": FOLLOWUP_PREFIX + digest([context.key, row["contact_id"]])}

    def _known(self, context, opportunity):
        task_id = self.contacts.task_id(context, opportunity)
        return (self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,))
                or self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,)))

    def select(self, context, preferences, at):
        if (context.scope.kind is not ScopeKind.PRIVATE or not preferences.values["screen_glance_enabled"]
                or preferences.reason("screen") or not preferences.values["automatic_enabled"]
                or self._cooling_down(context, preferences, at)
                or self._daily_count(context, preferences, at) >= preferences.values["screen_glance_daily_limit"]):
            return None
        rows = self.runtime.read_all("""SELECT f.feedback_id, f.capture_id, f.created_at
            FROM screen_feedback_anchors f JOIN screen_captures c ON c.capture_id = f.capture_id
            JOIN sources s ON s.source_id = c.source_id AND s.lineage_id = c.source_lineage_id
                AND s.source_revision = c.source_revision
            WHERE f.feedback_kind = 'proactive' AND s.installation_id = ? AND s.platform = ?
              AND s.scope_kind = ? AND s.native_scope_id = ? AND f.created_at > ? AND f.created_at <= ?
            ORDER BY f.created_at DESC, f.feedback_id DESC LIMIT ?""",
            (context.scope.installation_id, context.scope.platform, context.scope.kind.value,
             context.scope.native_scope_id, stamp(at - MAX_AGE), stamp(at), PAGE_SIZE))
        for row in rows:
            try:
                reference = require(self.screens.published_reference(row["capture_id"], scope=context.scope))
                opportunity = self._opportunity(context, row["feedback_id"],
                    datetime.fromisoformat(row["created_at"]), reference)
                if not opportunity.opened_at <= at < opportunity.expires_at or self._known(context, opportunity):
                    continue
                self._material(context, row["feedback_id"], row["capture_id"], at)
                return self._project(context, row["feedback_id"], row["capture_id"], at)
            except (TaskError, KeyError, ValueError):
                continue
        return None

    async def diagnostic(self, context, peek, *, test_id, role_instruction):
        """Capture once, interpret that original, and select only its new feedback."""
        stages = []
        at = self.tasks.now()
        if peek is None or not peek.ready(context, at):
            raise DiagnosticSourceError("screen_peek_unavailable",
                "当前窗口的截图设备、识屏开关或窥屏授权不可用", stage="screen_capture")
        try:
            peek.app.screen_interpretation.check_model_route(context, role_instruction=role_instruction)
        except TaskError as error:
            reason = ("屏幕解读需要支持图片的模型；请检查主模型和备用模型。本次未采集截图。"
                      if error.code == "model_capability_mismatch" else str(error))
            raise DiagnosticSourceError(error.code, reason, stage="screen_interpretation") from error
        task_id = "screen-peek-diagnostic:" + digest([context.key, test_id])
        decision = {"purpose": "diagnostic", "episode_at": at, "task_id": task_id}
        if peek.request(context, decision, request_ref=test_id, role_instruction=role_instruction) is None:
            raise DiagnosticSourceError("screen_peek_unavailable",
                "本次截图任务没有启动；已有任务不会再次执行", stage="screen_capture", task_id=task_id)
        deadline = asyncio.get_running_loop().time() + 130

        async def completed(identifier, stage):
            while asyncio.get_running_loop().time() < deadline:
                task = require(self.tasks.read(context, identifier))
                if task.state == "succeeded" and task.result_ref:
                    return task.result_ref
                if task.state in ("failed", "cancelled", "expired", "uncertain", "dead_letter"):
                    reason = task.reason
                    if stage == "screen_capture":
                        reason = peek.pending.get(identifier, {}).get("error_code") or reason
                    elif peek.app is not None:
                        reason = peek.app.screen_interpretation.pending.get(identifier, {}).get("error_code") or reason
                    unknown = task.state == "uncertain" or reason in (
                        "screen_peek_unknown", "screen_interpretation_unknown", "model_result_unknown",
                        "model_timeout", "model_usage_unknown")
                    raise DiagnosticSourceError(reason or "screen_diagnostic_failed",
                        "截图结果未确认" if unknown and stage == "screen_capture" else
                        "视觉分析结果未确认" if unknown else "本次截图或视觉分析任务未成功：" + (reason or task.state),
                        stage=stage, stages=stages, state="unknown" if unknown else "failed", task_id=identifier)
                await asyncio.sleep(0.2)
            raise DiagnosticSourceError("screen_diagnostic_pending",
                "本次截图或视觉分析仍未完成，请核对任务记录，不要重新运行",
                stage=stage, stages=stages, state="pending", task_id=identifier)

        interpretation_id = await completed(task_id, "screen_capture")
        stages.append({"stage": "screen_capture", "state": "passed", "detail": "本次设备已返回并保存真实截图"})
        analysis_id = await completed(interpretation_id, "screen_interpretation")
        row = self.runtime.read_one("""SELECT feedback_id, capture_id FROM screen_feedback_anchors
            WHERE analysis_id = ? AND feedback_kind = 'proactive' ORDER BY created_at DESC LIMIT 1""", (analysis_id,))
        if row is None:
            raise DiagnosticSourceError("contact_screen_feedback_unavailable",
                "本次视觉模型没有生成可分享的屏幕观察", stage="screen_interpretation", stages=stages,
                task_id=interpretation_id)
        try:
            candidate = self._project(context, row["feedback_id"], row["capture_id"], self.tasks.now())
        except TaskError as error:
            raise DiagnosticSourceError(error.code, str(error), stage="screen_interpretation", stages=stages,
                task_id=interpretation_id) from error
        stages.append({"stage": "screen_interpretation", "state": "passed", "detail": "视觉模型已分析本次截图"})
        return candidate, stages

    def _validate_source(self, record, at):
        try:
            body = json.loads(record.payload)
            receipt = body.pop("_receipt")
            context = TaskContext.restore(receipt["context"])
            reference, result, text = self._material(context, receipt["feedback_id"], receipt["capture_id"], at)
            expected_source = self._reference(context, receipt["feedback_id"], result.analysis)
            expected = {"event": "authorized_screen_observation", "observed_at": stamp(result.analysis.created_at),
                "interpretation": text,
                "meaning": "这是已授权 Screen 对当时可见画面的模型解读，不是屏幕原文、用户经历或当前画面；只分享明确可见且仍相关的内容。"}
            if (record.reference != expected_source or record.audience != context.audience or body != expected
                    or receipt["analysis_hash"] != digest(result.analysis) or record.content_hash != digest(record.payload)):
                raise ValueError("Screen source changed")
            return None
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_screen_source_changed", "original Screen analysis is no longer available") from error

    def validate(self, context, marker, at):
        if type(marker) is not dict or set(marker) != {
                "feedback_id", "capture_id", "analysis_hash", "expires_at", "source"}:
            raise TaskError("contact_screen_invalid", "Screen contact marker is invalid")
        from companion_v2.conversation.messages import source_from_document
        try:
            source = source_from_document(marker["source"])
            reference, result, _ = self._material(context, marker["feedback_id"], marker["capture_id"], at)
            opportunity = self._opportunity(context, marker["feedback_id"], result.analysis.created_at, reference)
            if (source != self._reference(context, marker["feedback_id"], result.analysis)
                    or marker["analysis_hash"] != digest(result.analysis)
                    or marker["expires_at"] != stamp(opportunity.expires_at)
                    or not opportunity.opened_at <= at < opportunity.expires_at):
                raise ValueError("Screen contact changed")
            require(self.contacts.sources.validate_reference_for_audience(
                source, recipient=context.actor.subject, observed_at=at))
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_screen_changed", "Screen contact is no longer current") from error
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        preferences.require_contact("screen")
