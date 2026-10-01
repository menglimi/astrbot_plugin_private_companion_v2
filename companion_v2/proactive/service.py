"""One explicit opportunity, one supervised model decision, one durable delivery.

Trusted producers, including the conversation scheduler, supply the cause and
current persona; interrupted model work is never silently replayed.
"""

import asyncio
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
import json
import logging
import re
from zoneinfo import ZoneInfo

from companion_v2.capabilities.memory_push import (DEFAULT_MEMORY_PUSH, PUSH_PROACTIVE_MESSAGE, MemoryPushRecord,
    push_memory, push_memory_id)
from companion_v2.configuration.models import ConfigurationError
from companion_v2.conversation.messages import source_from_document
from companion_v2.conversation.reply_preparation import observed_statements
from companion_v2.conversation.reply_settings import ReplySettings
from companion_v2.conversation.text_processing import TEXT_DEFAULTS, text_policy
from companion_v2.delivery.media import image_manifest, manifest_hash
from companion_v2.delivery.plan import DeliveryContent, PokePlan, VoicePlan
from companion_v2.delivery.service import DeliveryRequest
from companion_v2.delivery.history import HistoricalText, VERSION as HISTORY_VERSION
from companion_v2.execution.models import (Lane, ProviderBinding, SideEffect, TaskDefinition, TaskError,
    TaskRegistration, TaskResult, TaskSpec, digest, encode, require, stamp)
from companion_v2.execution.runner import ExactTaskRunner, RunResult
from companion_v2.execution.service import outcome
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import OperationRef, VersionRef, normalize_utc
from companion_v2.model_gateway.models import ModelTaskProfile
from companion_v2.relationships.private_access import REVOCABLE_ABSENCE_CODES
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from .configuration import GROUP
from .budget import ContactBudget
from .contact_models import ContactIntent, ContactJob
from .persona_judge import (KIND as JUDGE_KIND, PersonaJudge, JudgeVerdict, exempt_purposes, judge_output,
                            judge_request, signature_for)
from .planner import ProactivePlanner
from .preferences import ProactivePreferences
from .prompts import contact_output, request_for
from .official_alert_events import SOURCE_OWNER as OFFICIAL_ALERT_SOURCE_OWNER, attribution_suffix


CONTACT_KIND = "proactive.compose"
JUDGE_TIMEOUT_SECONDS = 90
logger = logging.getLogger(__name__)


def contact_profile(provider, *, max_output_tokens=1024):
    return ModelTaskProfile(CONTACT_KIND, Lane.BACKGROUND, provider,
        "保持原人格；基于真实来源决定是否主动联系，允许没有合适内容时不发送。", max_output_tokens=max_output_tokens)


def _push_scope(kind):
    """推送用的会话口径：对外只区分私聊与群聊，其余一律 ``unknown``。

    V2 自己的 ScopeKind 里还有 thread/device/system，那些不是接收方认识的口径；
    硬塞过去只会让它在可见性判定里走进一条没人验证过的分支。
    """

    value = getattr(kind, "value", "")
    return value if value in ("private", "group") else "unknown"


def persona_judge_profile(provider, *, max_output_tokens=260):
    """The post-draft persona judgement, as its own registered background task.

    The host registers this profile next to the contact profile; without it the
    judgement is unavailable and an enabled judge withholds the contact instead
    of sending it unjudged.
    """
    return ModelTaskProfile(JUDGE_KIND, Lane.BACKGROUND, provider,
        "按当前人格与世界观点评一条已写好的主动消息，只决定放行或拦下。", max_output_tokens=max_output_tokens)


def single_line(text, limit):
    """The spoken span of one sealed body: whitespace collapsed, then truncated.

    V1 capped proactive speech with the same normalization, so a multi-line
    contact never reads a newline or a task marker aloud.
    """
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def local_day_start(at, timezone_name):
    """The first instant of the relationship's local day, expressed in UTC.

    ``proactive_contacts`` only stores UTC instants. The relationship's own
    configured timezone is the one clock its quiet hours already use, so the
    daily poke allowance resets at that local midnight without another table,
    counter or migration.
    """
    zone = ZoneInfo(timezone_name)
    local = normalize_utc(at, field="contact expression time").astimezone(zone)
    return datetime.combine(local.date(), time.min, tzinfo=zone).astimezone(timezone.utc)


class ProactiveContacts:
    def __init__(self, configuration, memory_push=None):
        self.configuration, self.runtime = configuration, configuration.runtime
        # 推送端口是旁路：它记录角色说过的话，但不参与「说不说、说什么」的决定。
        self.memory_push = DEFAULT_MEMORY_PUSH if memory_push is None else memory_push
        self.sources, self.operations = SourceRepository(self.runtime), OperationRepository(self.runtime)
        self.budget = ContactBudget(self.runtime)
        self.history = self.schedule = self.semantics = None
        # Optional: an unwired host or an unavailable memory leaves proactive
        # contact exactly as it was, and a memory failure never withholds a
        # message the user may be waiting for.
        self.memory_context = None
        self.persona_judge = PersonaJudge(self.runtime)
        self._pending, self._invocations = {}, set()
        self._closed = False
        self.gateway = self.runner = self.generation = self.judge_runner = None
        self.registrations = (TaskRegistration(TaskDefinition(CONTACT_KIND, GROUP, GROUP, Lane.BACKGROUND,
            side_effect=SideEffect.LOCAL, binding=ProviderBinding(GROUP, "local", "1", "contact-worker-1"),
            timeout_seconds=180, max_attempts=1, concurrency=2), self.validate),
            TaskRegistration(TaskDefinition(JUDGE_KIND, GROUP, GROUP, Lane.BACKGROUND,
                side_effect=SideEffect.LOCAL, binding=ProviderBinding(GROUP, "local", "1", "contact-judge-1"),
                timeout_seconds=JUDGE_TIMEOUT_SECONDS, max_attempts=1, concurrency=2), self.validate_judge))

    def attach(self, gateway, delivery, *, require_running, notify):
        if self.gateway is not None or gateway.runtime is not self.runtime or delivery.runtime is not self.runtime:
            raise ValueError("contact worker must share its original gateway and delivery runtime")
        self.gateway, self.delivery, self.tasks = gateway, delivery, gateway.tasks
        self.require_running, self.notify = require_running, notify
        self.preferences = ProactivePreferences(self.configuration, self.tasks)
        self.runner = ExactTaskRunner(self.tasks, frozenset({CONTACT_KIND}), self._generate)
        self.judge_runner = ExactTaskRunner(self.tasks, frozenset({JUDGE_KIND}), self._judge_generate)

    def attach_semantics(self, semantics):
        if self.semantics is not None or semantics.app.runtime is not self.runtime:
            raise ValueError("contact reactions require the original semantic service")
        self.semantics = semantics

    def attach_memory(self, memory):
        """Bind the relationship's memory read owner, exactly as replies do.

        The host passes the same service ``ConversationMessages`` receives, so a
        proactive message and a reply read one memory. The binding fails loudly
        at construction time instead of silently dropping every later contact's
        memory material, but it stays optional: a host that never calls this
        keeps today's behaviour.
        """
        if memory is None or memory.runtime is not self.runtime:
            raise ValueError("proactive memory must use the contact worker's original runtime")
        if self.memory_context is not None and self.memory_context is not memory.context:
            raise ValueError("proactive memory owner cannot be replaced")
        self.memory_context = memory.context

    def _memory_materials(self, job, records):
        """Recall this relationship's memory for one contact, or nothing.

        Read-only and best effort: a disabled memory, a moved role binding, a
        forgotten source or any storage failure degrades to "no material"
        instead of stopping the message. ``job.context.actor`` is already the
        authenticated owner of this opportunity, and every read rechecks it.
        """
        if self.memory_context is None:
            return ()
        try:
            sources = tuple(record.reference for record in records)
            session_key = "memory-contact-" + digest(job.request_hash)
            # The opportunity's own possibility and the exact selected source
            # bodies are this contact's "current text", so topical recall and the
            # "does this contact ask about eating" habit question see the same
            # input a reply would see. The key stays bounded because it is
            # derived from the task itself, never from model text.
            snapshot = self.memory_context.contact_capture(job.context, session_key, sources, job.deadline_at)
            return self.memory_context.contact_contributions(snapshot, job.context)
        except Exception as error:
            # Memory is optional material for a message the user may already be
            # waiting for: an unavailable owner or an unexpected storage failure
            # must degrade to "no material", never to a withheld contact.
            logger.warning("V2 proactive memory recall was unavailable: %s", type(error).__name__)
            return ()

    def _reaction_available(self, context, contact_id):
        if self.semantics is None:
            return False
        return self.semantics.proactive_reaction_available(context, contact_id)

    def _last_plan_at(self, context, name):
        """When this relationship last sealed a voice or poke plan, if ever."""
        document_path = {"voice": "$.voice", "poke": "$.poke"}[name]
        row = self.runtime.read_one("""SELECT created_at FROM proactive_contacts
            WHERE origin_key = ? AND json_extract(record_json, ?) IS NOT NULL
            ORDER BY created_at DESC LIMIT 1""", (context.key, document_path))
        return datetime.fromisoformat(row["created_at"]) if row is not None else None

    def _planned_pokes(self, context, preferences, at):
        """How many pokes this relationship already sealed during its local day.

        A sealed plan reserves the allowance even when the wire effect later
        fails or stays unknown: the action may already have reached the
        recipient, so a retry must not exceed the configured count.
        """
        start = local_day_start(at, preferences.values["quiet_timezone"])
        return self.runtime.read_one("""SELECT COUNT(*) FROM proactive_contacts
            WHERE origin_key = ? AND created_at >= ? AND json_extract(record_json, '$.poke') IS NOT NULL""",
            (context.key, stamp(start)))[0]

    def _voice_available(self, context, preferences, at):
        if not preferences.values["voice_action_enabled"]:
            return False
        minutes = preferences.values["voice_action_cooldown_minutes"]
        last = self._last_plan_at(context, "voice") if minutes > 0 else None
        return last is None or at >= last + timedelta(minutes=minutes)

    def _poke_available(self, context, preferences, at):
        limit = preferences.values["poke_action_daily_limit"]
        if not preferences.values["poke_action_enabled"] or limit <= 0:
            return False
        if self._planned_pokes(context, preferences, at) >= limit:
            return False
        minutes = preferences.values["poke_action_cooldown_minutes"]
        last = self._last_plan_at(context, "poke") if minutes > 0 else None
        return last is None or at >= last + timedelta(minutes=minutes)

    def _expression_plans(self, context, preferences, body, decision, at):
        """Decide what may leave, from model intent plus the relationship's own accounting.

        The model only says that a voice note or a poke would suit the moment.
        Availability, cooldown and the daily allowance are read back from sealed
        contacts here, so a fabricated, replayed or stale intent cannot exceed
        them. A body the guards cleared never carries either side effect.
        """
        if body is None or not body.strip():
            return None, None
        voice = poke = None
        if decision.get("voice_intent") is True and self._voice_available(context, preferences, at):
            speech = single_line(body, preferences.values["voice_action_max_chars"])
            if speech:
                voice = VoicePlan(speech)
        if decision.get("poke_intent") is True and self._poke_available(context, preferences, at):
            poke = PokePlan(count=1)
        return voice, poke

    def start(self):
        row = self.runtime.read_one("SELECT generation FROM configuration_consumers WHERE consumer_id = ?", (GROUP,))
        self.generation = self.configuration.start_consumer(GROUP, expected_generation=row["generation"] if row else 0)

    def proactive_denied(self, context, *, at=None):
        """主动权限被操作员收回了吗（只判定，不写任何状态）。

        收回 ``proactive.contact`` 之后，规划这一步不该再往下走：既省掉一次配置读取，
        也让"为什么没主动联系他"有个明确原因。真故障（绑定变了、作用域不对）不在这里
        吞掉——那些仍然照旧抛出，由上层按失败处理。
        """
        at = at or self.tasks.now()
        result = self.tasks.check_context_access(context, action=GROUP, observed_at=at)
        if result.is_success:
            return False
        return result.failure.code in REVOCABLE_ABSENCE_CODES

    def _policy(self, context, purpose, at, *, token=None, contact_id=""):
        preferences = require(self.preferences.read(context, observed_at=at))
        preferences.require_contact(purpose)
        if token is not None and preferences.snapshot.resolution_token != token:
            raise TaskError("contact_preferences_changed", "prepared contact belongs to earlier preferences")
        self.budget.contacts(context, preferences, at, exclude_contact_id=contact_id)
        return preferences

    @staticmethod
    def task_id(context, opportunity):
        return "contact-task-" + digest([context.scope.key, opportunity.opportunity_id])

    def _continuity(self, context, history, interaction, origin, at, *, last_reply=None):
        if history is not None:
            if self.history is None:
                raise TaskError("delivery_history_unavailable", "contact requires its original history owner")
            self.history.read(history, context, at, action=GROUP)
        if last_reply is not None:
            if self.history is None:
                raise TaskError("delivery_history_unavailable", "contact requires its original reply history")
            self.history.verify_reply(last_reply, context, at)
        if interaction is not None and self.history.interaction(context, at, action=GROUP)["latest_input"] != interaction["latest_input"]:
            raise TaskError("contact_conversation_changed", "a new or withdrawn input superseded the contact decision")
        if origin is not None:
            if self.schedule is None:
                raise TaskError("contact_schedule_unavailable", "automatic contact requires its original scheduler")
            self.schedule.validate_origin(context, origin, at)

    def _adopt(self, context, preferences):
        # The persisted receipt survives restart and transactional rollback;
        # an unchanged polling pass must not rewrite it every second.
        row = self.runtime.read_one("""SELECT a.state, a.resolution_token, a.generation FROM configuration_applications a
            JOIN configuration_consumers c ON c.consumer_id = a.consumer_id AND c.generation = a.generation
            WHERE a.target_key = ? AND a.group_id = ? AND a.consumer_id = ?""",
            (preferences.snapshot.target.key, GROUP, GROUP))
        if (row is not None and row["generation"] == self.generation and row["state"] == "applied"
                and row["resolution_token"] == preferences.snapshot.resolution_token):
            return
        require(self.configuration.report_application(context.actor, snapshot=preferences.snapshot,
            generation=self.generation, succeeded=True, observed_at=preferences.observed_at))

    def _records(self, context, sources, at, *, hashes=None):
        records = []
        for source in sources:
            if source.scope != context.scope:
                raise TaskError("contact_source_scope", "contact evidence belongs to another window")
            require(self.sources.validate_reference(source, observed_at=at))
            record = require(self.sources.read(source, resolved=context.actor, capability="text",
                observed_at=at, authorizer=self.tasks.identity))
            if not set(context.audience.recipients).issubset(record.audience.recipients):
                raise TaskError("source_audience_mismatch", "contact evidence is unavailable to its original audience")
            if digest(record.payload) != record.content_hash:
                raise TaskError("contact_source_changed", "contact evidence no longer matches its stored hash")
            records.append(record)
        if hashes is not None and tuple(record.content_hash for record in records) != hashes:
            raise TaskError("contact_source_changed", "contact evidence changed after selection")
        return tuple(records)

    def _duplicate(self, context, body, preferences, at, *, purpose, contact_id="", origin=None):
        if not body or not preferences.dedup_applies(purpose, origin) or self.history is None:
            return False
        weather = origin is not None and any(key in origin for key in
            ("weather_event", "weather_change_event", "official_alert_event"))
        minutes = preferences.values["dedup_weather_window_minutes" if weather else "dedup_sent_window_minutes"]
        normalized = " ".join(body.split())
        cutoff = stamp(at - timedelta(minutes=minutes)) if minutes else ""
        current = self.runtime.read_one("SELECT created_at FROM proactive_contacts WHERE contact_id = ?", (contact_id,))
        rows = self.runtime.read_all("""SELECT c.contact_id, c.body, c.created_at, d.*
            FROM proactive_contacts c JOIN background_deliveries d
                ON json_extract(d.request_json, '$.source_ref') = c.contact_id
            WHERE c.origin_key = ? AND c.contact_id != ? AND d.owner = ?
            AND ((d.state = 'delivered' AND d.delivered_at >= ? AND d.delivered_at <= ?)
              OR (d.state IN ('pending', 'dispatched', 'accepted', 'unknown') AND c.created_at >= ?))
            ORDER BY c.created_at DESC, c.contact_id DESC""",
            (context.key, contact_id, GROUP, cutoff, stamp(at), cutoff))
        for row in rows:
            if " ".join(row["body"].split()) != normalized:
                continue
            if row["state"] != "delivered":
                if current is None or (row["created_at"], row["contact_id"]) < (current["created_at"], contact_id):
                    return True
                continue
            snapshot = {"version": HISTORY_VERSION, "context_key": context.key,
                        "references": [self.history.reference(row)]}
            try:
                if self.history.read(snapshot, context, at, action=GROUP)[0]["text"] == row["body"]:
                    return True
            except TaskError:
                continue
        if preferences.values["dedup_last_message_enabled"]:
            last = self.history.latest_reply(context, at,
                within_minutes=preferences.values["dedup_last_message_window_minutes"], action=GROUP)
            return last is not None and " ".join(last["text"].split()) == normalized
        return False

    async def contact(self, context, opportunity, intents, *, role_instruction, selection_seed, automatic_origin=None):
        """Trusted producer API; no model may fabricate its cause, identity or persona."""
        if self.runner is None:
            raise ValueError("contact worker has not been attached")
        if self._closed:
            return Outcome.failed("task_runner_closed", "contact worker is closed")
        if (not isinstance(intents, tuple) or not 1 <= len(intents) <= 32
                or any(not isinstance(i, ContactIntent) or i.thought.opportunity != opportunity for i in intents)
                or len({i.thought.thought_id for i in intents}) != len(intents)):
            raise ValueError("contact opportunity requires bounded unique thoughts for this exact opportunity")
        if (not isinstance(role_instruction, str) or not role_instruction.strip() or len(role_instruction) > 65536
                or not isinstance(selection_seed, str) or not selection_seed.strip() or len(selection_seed) > 256):
            raise ValueError("contact requires its original persona and stable selection seed")
        if opportunity.scope != context.scope:
            return Outcome.failed("contact_context_mismatch", "opportunity belongs to another original window")
        task_id = self.task_id(context, opportunity)
        inputs = [context.key, opportunity, intents, role_instruction, selection_seed]
        request_hash = digest(inputs + [automatic_origin] if automatic_origin is not None else inputs)
        try:
            self.require_running()
            if CONTACT_KIND not in self.gateway.router.profiles:
                raise TaskError("model_task_unregistered", "contact requires its own explicit background model profile")
            require(self.tasks.authorize_context(context, action=GROUP, observed_at=self.tasks.now()))
            initial_preferences = require(self.preferences.read(context, observed_at=self.tasks.now()))
            self._adopt(context, initial_preferences)
            invocation = None
            registered = False
            try:
                # Keep quota checks and durable task admission in one SQLite
                # write transaction so another worker cannot reserve the same
                # relationship allowance from a different private window.
                with self.runtime.transaction():
                    require(self.tasks.authorize_context(context, action=GROUP, observed_at=self.tasks.now()))
                    prior = self.runtime.read_one("SELECT task_id FROM execution_tasks WHERE task_id = ?", (task_id,))
                    if prior is not None:
                        task = require(self.tasks.read(context, task_id))
                        if task.spec.kind != CONTACT_KIND or task.spec.request_ref != request_hash:
                            raise TaskError("contact_request_conflict", "opportunity cannot change its original inputs or authority")
                        return Outcome.success(RunResult(task))
                    if self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,)):
                        raise TaskError("contact_request_retired", "original contact remains archived and cannot be regenerated")
                    at = self.tasks.now()
                    if not opportunity.opened_at <= at < opportunity.expires_at:
                        raise TaskError("opportunity_not_current", "opportunity is not currently open")
                    preferences = require(self.preferences.read(context, observed_at=at))
                    if preferences.snapshot.resolution_token != initial_preferences.snapshot.resolution_token:
                        raise TaskError("contact_preferences_changed", "contact policy changed before task admission")
                    self.budget.attempts(context, preferences, at)
                    self.budget.contacts(context, preferences, at)
                    if automatic_origin is not None and automatic_origin.get("role_hash") != digest(role_instruction):
                        raise TaskError("contact_persona_changed", "automatic contact must keep its original role instruction")
                    history = (self.history.capture(context, at, action=GROUP,
                                limit=preferences.values["generation_history_limit"],
                                max_chars=preferences.values["history_max_chars"])
                               if self.history is not None else None)
                    interaction = self.history.interaction(context, at, action=GROUP) if self.history is not None else None
                    self._continuity(context, history, interaction, automatic_origin, at)
                    feasible, originals, records_by_id = [], {}, {}
                    for intent in intents:
                        if preferences.reason(intent.purpose):
                            continue
                        try:
                            records = self._records(context, intent.thought.evidence.sources, at)
                        except TaskError:
                            continue
                        if intent.thought.evidence.captured_at > at:
                            continue
                        # Preference weights affect this competition only, never rights or scheduling.
                        weight = preferences.weight(intent.purpose)
                        if automatic_origin is not None:
                            prior = self.runtime.read_one("""SELECT record_json FROM proactive_contacts
                                WHERE origin_key = ? AND json_extract(record_json, '$.purpose') = ?
                                ORDER BY created_at DESC LIMIT 1""", (context.key, intent.purpose))
                            if prior is not None:
                                previous = json.loads(prior["record_json"])
                                feedback = previous.get("silence_feedback", {})
                                if (previous.get("purpose") == intent.purpose and feedback.get("confident_skip")):
                                    penalty = preferences.values["silence_feedback_penalty"]
                                    weight *= max(0.25, 1.0 - penalty)
                        thought = replace(intent.thought, weight=weight * intent.thought.weight)
                        feasible.append(thought)
                        originals[thought.thought_id], records_by_id[thought.thought_id] = intent, records
                    selection = require(ProactivePlanner().select(opportunity, tuple(feasible),
                        observed_at=at, selection_seed=selection_seed))
                    intent = originals[selection.selected.thought_id]
                    records = records_by_id[intent.thought.thought_id]
                    job = ContactJob(context, intent, role_instruction, request_hash,
                        preferences.snapshot.resolution_token, tuple(record.content_hash for record in records),
                        selection.feasible_count, selection.weight_used, history, interaction, automatic_origin)
                    presentation = ReplySettings(self.configuration).capture(context, at)["settings"]
                    job = replace(job, presentation_settings={key: presentation[key] for key in TEXT_DEFAULTS},
                                  deadline_at=opportunity.expires_at)
                    self._pending[task_id] = job
                    invocation = asyncio.current_task()
                    self._invocations.add(invocation)
                    registered = True
                    require(self.tasks.submit(TaskSpec(task_id, context, CONTACT_KIND, request_hash, task_id,
                        opportunity.opened_at, opportunity.expires_at)))
            except BaseException:
                if registered:
                    self._pending.pop(task_id, None)
                    self._invocations.discard(invocation)
                raise
            try:
                result = await self.runner.run(context, task_id)
                if result.is_success and (result.unwrap().task is None or result.unwrap().task.state in ("created", "retry_scheduled")):
                    task = require(self.tasks.discard_queued(task_id, reason="owner_unavailable"))
                    return Outcome.success(RunResult(task))
                return result
            finally:
                self._pending.pop(task_id, None)
                self._invocations.discard(invocation)
        except (TaskError, ConfigurationError) as error:
            return Outcome.failed(error.code, str(error))

    @outcome
    def validate(self, spec, at):
        self.require_running()
        job = self._pending.get(spec.task_id)
        if (job is None or spec.kind != CONTACT_KIND or job.request_hash != spec.request_ref
                or job.context != spec.context or spec.not_before != job.intent.thought.opportunity.opened_at
                or spec.deadline_at != job.intent.thought.opportunity.expires_at):
            raise TaskError("contact_request_unavailable", "original contact inputs are no longer held")
        preferences = self._policy(job.context, job.intent.purpose, at, token=job.preference_token,
                                   contact_id="contact-" + digest(spec.task_id))
        self.budget.attempts(job.context, preferences, at, exclude_task_id=spec.task_id)
        self._records(job.context, job.intent.thought.evidence.sources, at, hashes=job.source_hashes)
        self._continuity(job.context, job.history, job.interaction, job.automatic_origin, at, last_reply=job.last_reply)
        return True

    async def _generate(self, run):
        job = self._pending[run.task.task_id]
        at = self.tasks.now()
        preferences = self._policy(job.context, job.intent.purpose, at, token=job.preference_token)
        records = self._records(job.context, job.intent.thought.evidence.sources, at, hashes=job.source_hashes)
        contact_id = "contact-" + digest(run.task.task_id)
        try:
            reactions_available = self._reaction_available(job.context, contact_id)
        except Exception:
            reactions_available = False
        try:
            voice_available = self._voice_available(job.context, preferences, at)
            poke_available = self._poke_available(job.context, preferences, at)
        except Exception:
            voice_available = poke_available = False
        completion = None
        try:
            history = self.history.read(job.history, job.context, at, action=GROUP) if job.history is not None else ()
            last_reply = (self.history.latest_reply(job.context, at,
                within_minutes=preferences.values["dedup_last_message_window_minutes"], action=GROUP)
                if self.history is not None and preferences.dedup_applies(job.intent.purpose, job.automatic_origin)
                and preferences.values["dedup_last_message_enabled"] else None)
            if last_reply is not None:
                job = replace(job, last_reply=last_reply["reference"])
                self._pending[run.task.task_id] = job
            presentation = text_policy(job.presentation_settings or {})
            request = request_for(job, records, preferences, history,
                last_reply=last_reply, reactions_available=reactions_available,
                voice_available=voice_available, poke_available=poke_available,
                memory=self._memory_materials(job, records))
            if presentation.instruction:
                request = replace(request, instruction=request.instruction + "\n" + presentation.instruction)
            completion = await self.gateway.generate(run, request)
            if completion.draft is None:
                raise ValueError("contact generation requires a final decision")
            alert_records = ([record for record in records if record.reference.owner == OFFICIAL_ALERT_SOURCE_OWNER]
                             if job.automatic_origin is not None and "official_alert_event" in job.automatic_origin else [])
            if job.automatic_origin is not None and "official_alert_event" in job.automatic_origin and len(alert_records) != 1:
                raise TaskError("contact_official_alert_invalid", "official alert attribution source is unavailable")
            alert_material = json.loads(alert_records[0].payload) if alert_records else None
            body, reaction_intent = contact_output(completion.draft.text, official_alert=alert_material)
            decision_data = json.loads(completion.draft.text)
            decision_confidence = float(decision_data.get("decision_confidence", 1.0))
            confidence_skip = body is not None and decision_confidence < preferences.values["silence_min_confidence"]
            if confidence_skip:
                body, reaction_intent = None, None
            run.validate()
            presentation_reason = None
            if body is not None:
                body, leaked = presentation.framework_guard(body)
                if not leaked:
                    statements = (body,) if alert_material else observed_statements(completion.draft)
                    body = presentation.replace_text(body, statements=statements)
                    body = presentation.clean_parts((body,), statements=statements)[0]
                else:
                    presentation_reason = "framework_guard"
                if not body.strip():
                    body, reaction_intent = None, None
                    presentation_reason = "presentation_empty"
            if body is not None and job.automatic_origin is not None and "official_alert_event" in job.automatic_origin:
                attributions = alert_material["attributions"]
                if (type(attributions) is not list or not attributions
                        or any(type(item) is not str or not item for item in attributions)):
                    raise TaskError("contact_official_alert_invalid", "official alert attribution is unavailable")
                body += attribution_suffix(attributions)
            if body is not None and presentation.forbidden_word_guard(
                    body, scope_kind=job.context.scope.kind.value) is not None:
                body, reaction_intent = None, None
                presentation_reason = "forbidden_word"
            dedup_reason = None
            if body is not None and self._duplicate(job.context, body, preferences, self.tasks.now(),
                    purpose=job.intent.purpose, origin=job.automatic_origin):
                body, reaction_intent = None, None
                dedup_reason = "exact_repeat"
            judge, judge_task = None, None
            if body is not None:
                judge, judge_task = self._judge_plan(job, body, preferences, self.tasks.now())
                if judge is not None and not judge.allowed and not judge.pending:
                    body, reaction_intent = None, None
                    presentation_reason = "persona_judge"
            offered = None
            # An image offer publishes original bytes, so it is never chosen before a
            # pending judgement: the judged payload stays body-only until it is allowed.
            if body is not None and reaction_intent and reactions_available and judge_task is None:
                try:
                    if self._reaction_available(job.context, contact_id):
                        offered = await self.semantics.reactions.select_for_contact(job.context, reaction_intent)
                except (TaskError, ValueError, OSError):
                    offered = None
            run.validate()
            operation = OperationRef("save-" + contact_id, GROUP, job.context.scope, VersionRef(contact_id, 1), contact_id)
            document = {"decision": "skip" if body is None else
                            "judge_pending" if judge_task is not None else "send",
                "purpose": job.intent.purpose, "preference_token": job.preference_token,
                "sources": job.intent.thought.evidence.sources, "source_hashes": job.source_hashes,
                "opened_at": job.intent.thought.opportunity.opened_at, "expires_at": job.intent.thought.opportunity.expires_at,
                "thought_id": job.intent.thought.thought_id, "feasible_count": job.feasible_count,
                "weight_used": job.weight_used, "call_id": completion.call_id,
                "history": job.history, "interaction": job.interaction, "automatic_origin": job.automatic_origin,
                "last_reply": job.last_reply, "dedup_reason": dedup_reason,
                "decision_confidence": decision_confidence,
                "judge": judge.document() if judge is not None else None,
                "silence_feedback": {"confident_skip": decision_data["decision"] == "skip"
                    and decision_confidence >= preferences.values["silence_min_confidence"]},
                "silence_reason": "below_confidence_threshold" if confidence_skip else None,
                "presentation_settings": job.presentation_settings, "presentation_reason": presentation_reason}
            with self.runtime.transaction() as connection:
                run.validate()
                if body is not None and self._duplicate(job.context, body, preferences, self.tasks.now(),
                        purpose=job.intent.purpose, origin=job.automatic_origin):
                    body, offered = None, None
                    document["decision"] = "skip"
                    document["dedup_reason"] = "exact_repeat"
                reaction = None
                if offered is not None:
                    try:
                        if self._reaction_available(job.context, contact_id):
                            with self.runtime.transaction():
                                issued_at = self.tasks.now()
                                image = self.semantics.reactions.contact_image(job.context, contact_id, offered, issued_at,
                                    publish=True, evidence=job.intent.thought.evidence.sources)
                                reaction = {**offered, "intent": reaction_intent, "issued_at": issued_at,
                                            "manifest": image_manifest(image)}
                    except (TaskError, ValueError, OSError):
                        reaction = None
                voice, poke = self._expression_plans(job.context, preferences, body, decision_data, self.tasks.now())
                payload_hash = manifest_hash(body or "", (reaction["manifest"],) if reaction else ())
                if reaction is not None:
                    document["reaction"] = reaction
                if voice is not None:
                    document["voice"] = voice.document()
                if poke is not None:
                    document["poke"] = poke.document()
                run.validate()
                run.begin_effect()
                require(self.operations.reserve(operation, parameter_hash=digest([job.request_hash, payload_hash]), observed_at=self.tasks.now()))
                connection.execute("INSERT INTO proactive_contacts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (contact_id, run.task.task_id, job.context.key, encode(document), body or "", payload_hash,
                     operation.operation_id, stamp(self.tasks.now())))
                require(self.operations.transition(operation.operation_id, expected_state=OperationState.ACCEPTED,
                    next_state=OperationState.COMPLETED, observed_at=self.tasks.now()))
                if judge_task is not None:
                    # The sealed draft is committed first; the judgement runs as its own
                    # background task and is the only path that may queue this delivery.
                    require(self.tasks.submit(TaskSpec(judge_task["task_id"], job.context, JUDGE_KIND,
                        judge_task["request_hash"], contact_id, self.tasks.now(), judge_task["deadline"])))
                elif body is not None:
                    require(self.delivery.queue(DeliveryRequest(GROUP, contact_id, job.context, contact_id, payload_hash,
                        job.intent.thought.opportunity.opened_at, job.intent.thought.opportunity.expires_at)))
                run.record_operation(operation.operation_id)
            self.notify()
            # ``body is not None and judge_task is None`` 恰好就是「事务里刚把这条消息
            # 排进投递」：待判定的分支只提交草稿，而重复检查一旦命中就把 body 置空。
            # 推送放在事务之外，不在 SQLite 写事务里 await 别家插件的写入。
            if body is not None and judge_task is None:
                await self._push_contact(job.context, contact_id, body, job.intent.purpose)
            return TaskResult("succeeded", effect="committed", result_ref=contact_id if body is not None else "contact-skipped:" + contact_id,
                              operation_id=operation.operation_id, receipt_ref=operation.operation_id)
        except BaseException:
            if completion is not None:
                self.gateway.ledger.discard(completion.call_id)
            raise

    def _judge_plan(self, job, body, preferences, at):
        """Decide whether this sealed body needs a model judgement before it may leave.

        Returns the resolved verdict, or the pending judge task the commit will
        submit. A judge that cannot run for a known reason withholds immediately;
        one that is merely outstanding leaves the draft sealed and undelivered.
        """
        values = preferences.values
        if not values["enable_llm_proactive_persona_judge"]:
            return None, None
        signature = signature_for(job.intent.purpose, body)
        if job.intent.purpose in exempt_purposes(preferences):
            return JudgeVerdict("send", 100, "该联系目的按配置豁免主动人格判定", signature, True), None
        cached = self.persona_judge.cached(job.context, signature, at,
            ttl_minutes=values["proactive_persona_judge_cache_minutes"],
            threshold=values["proactive_persona_judge_threshold"])
        if cached is not None:
            return cached, None
        if JUDGE_KIND not in self.gateway.router.profiles:
            return PersonaJudge.denied(signature, "judge_profile_unavailable",
                reason="主动人格判定模型档未注册，本次不发送"), None
        day_start = local_day_start(at, values["quiet_timezone"])
        if self.persona_judge.decided_today(job.context, day_start) >= values["proactive_persona_judge_daily_limit"]:
            return PersonaJudge.denied(signature, "judge_daily_limit",
                reason="主动人格判定达到当日调用上限，本次不发送"), None
        deadline = min(job.intent.thought.opportunity.expires_at, at + timedelta(seconds=JUDGE_TIMEOUT_SECONDS))
        if deadline <= at:
            return PersonaJudge.denied(signature, "judge_window_closed",
                reason="本次机会已无可判定时间，不发送未判定的正文"), None
        task_id = "contact-judge-" + digest([job.context.key, signature])
        verdict = PersonaJudge.pending(signature, task_id)
        return verdict, {"task_id": task_id, "signature": signature, "deadline": deadline,
                         "request_hash": digest([job.request_hash, signature])}

    @outcome
    def validate_judge(self, spec, at):
        self.require_running()
        if spec.kind != JUDGE_KIND or not spec.idempotency_key:
            raise TaskError("contact_judge_unavailable", "judgement must retain its sealed draft")
        row = self.runtime.read_one("""SELECT origin_key, record_json FROM proactive_contacts
            WHERE contact_id = ?""", (spec.idempotency_key,))
        if row is None or row["origin_key"] != spec.context.key:
            raise TaskError("contact_judge_unavailable", "judgement draft is unavailable")
        data = json.loads(row["record_json"])
        if data.get("decision") != "judge_pending" or (data.get("judge") or {}).get("task_id") != spec.task_id:
            raise TaskError("contact_judge_unavailable", "draft already has a resolved judgement")
        return True

    async def _judge_generate(self, run):
        context, at = run.task.spec.context, self.tasks.now()
        contact_id = run.task.spec.idempotency_key
        row = self.runtime.read_one("SELECT * FROM proactive_contacts WHERE contact_id = ?", (contact_id,))
        if row is None or row["origin_key"] != context.key:
            raise TaskError("contact_judge_unavailable", "judgement draft is unavailable")
        data = json.loads(row["record_json"])
        origin, judge = data.get("automatic_origin"), data.get("judge") or {}
        if data.get("decision") != "judge_pending" or judge.get("task_id") != run.task.task_id:
            raise TaskError("contact_judge_unavailable", "draft already has a resolved judgement")
        if not isinstance(origin, dict) or not origin.get("batch_id") or self.schedule is None:
            raise TaskError("contact_judge_persona_unavailable", "judgement needs the original accepted persona")
        self.schedule.validate_origin(context, origin, at)
        _, batch, _ = self.schedule._origin(context, origin["batch_id"], at)
        preferences = require(self.preferences.read(context, observed_at=at))
        preferences.require_contact(data["purpose"])
        entry = {"context": context, "purpose": data["purpose"], "body": row["body"], "at": stamp(at),
                 "note": preferences.values["note"], "confidence": data.get("decision_confidence", 1.0),
                 "role_instruction": batch["role_instruction"], "observed_at": at,
                 "cause_id": run.task.task_id}
        completion = await self.gateway.generate(run, judge_request(entry))
        if completion.draft is None:
            raise ValueError("persona judgement requires a final decision")
        try:
            decision, score, reason = judge_output(completion.draft.text)
        except (TypeError, ValueError):
            self.gateway.ledger.discard(completion.call_id)
            raise
        threshold = preferences.values["proactive_persona_judge_threshold"]
        allowed = decision == "send" and score >= threshold
        with self.runtime.transaction() as connection:
            run.validate()
            current = connection.execute("""SELECT record_json FROM proactive_contacts
                WHERE contact_id = ?""", (contact_id,)).fetchone()
            document = json.loads(current["record_json"])
            if (document.get("decision") != "judge_pending"
                    or (document.get("judge") or {}).get("task_id") != run.task.task_id):
                raise TaskError("contact_judge_unavailable", "draft already has a resolved judgement")
            document["decision"] = "send" if allowed else "skip"
            document["judge"] = {**judge, "state": "resolved", "decision": decision, "score": score,
                                 "reason": reason, "allowed": allowed, "cached": False,
                                 "model_call_id": completion.call_id, "failure": None}
            run.begin_effect()
            connection.execute("UPDATE proactive_contacts SET record_json = ? WHERE contact_id = ?",
                               (encode(document), contact_id))
            if allowed:
                require(self.delivery.queue(DeliveryRequest(GROUP, contact_id, context, contact_id,
                    row["payload_hash"], datetime.fromisoformat(document["opened_at"]),
                    datetime.fromisoformat(document["expires_at"]))))
        self.notify()
        if allowed:
            # 判定放行与直接发送是同一件事的两条互斥分支：草稿在此之前一直压着不发，
            # 现在它才真的排进投递，因此也在这里才写进记忆。反过来，把未获准的草稿
            # 提前推过去，会让牢插件记得一句角色从没说过的话。
            await self._push_contact(context, contact_id, row["body"], data.get("purpose"))
        return TaskResult("succeeded", effect="committed", result_ref=contact_id,
                          receipt_ref="proactive-judgement:" + run.task.task_id)

    async def _push_contact(self, context, contact_id, body, purpose):
        """把刚排进投递的主动消息推给对外表达记忆的一方；失败不影响这次投递。

        身份取自 ``contact_id``（它本来就是 ``digest(task_id)`` 的持久身份）：同一条
        草稿无论被重放几次，牢插件看到的都是同一个 ``memory_id``。
        """

        scope = context.scope
        record = MemoryPushRecord(
            memory_id=push_memory_id(PUSH_PROACTIVE_MESSAGE, "proactive", contact_id),
            content=f"Bot 主动联系对方时说：{body}",
            kind=PUSH_PROACTIVE_MESSAGE,
            scope=_push_scope(scope.kind),
            # V2 的核心没有平台会话 id，只有 ScopeRef；用 V2 自己的稳定命名空间，
            # 并且带上这一轮的原生会话，避免不同窗口的主动消息互相覆盖。
            session_id="private_companion_v2:proactive:" + (scope.native_scope_id or scope.conversation_id or "role"),
            platform=scope.platform,
            occurred_at=self.tasks.now().isoformat(),
            tags=("proactive", "proactive_message", "bot_action"),
            metadata=(
                ("event_type", "proactive_message"),
                ("action_label", "主动私聊"),
                ("purpose", purpose or ""),
                ("contact_id", contact_id),
                # 牢插件用这段正文写它自己的可见时间线，必须是真正发出去的那句话。
                ("clean_visible_text", body),
                ("query_anchors", ["主动消息", "主动私聊", "刚才主动说了什么", "最近主动联系"]),
            ),
            confidence=0.92,
            importance=0.58,
        )
        await push_memory(self.memory_push, record)

    def outstanding_judgements(self, *, limit=8):
        """Sealed drafts waiting for their judgement, oldest first."""
        return self.runtime.read_all("""SELECT c.contact_id, c.origin_key, t.task_id AS judge_task_id,
              t.state AS judge_state, t.record_json AS judge_record
            FROM proactive_contacts c LEFT JOIN execution_tasks t
              ON t.task_id = json_extract(c.record_json, '$.judge.task_id')
            WHERE json_extract(c.record_json, '$.decision') = 'judge_pending'
            ORDER BY c.created_at, c.contact_id LIMIT ?""", (limit,))

    @outcome
    def delivery_text(self, request, at):
        row, data, voice, poke = self._draft(request, at)
        if (request.not_before != datetime.fromisoformat(data["opened_at"])
                or request.deadline_at != datetime.fromisoformat(data["expires_at"])
                or not request.not_before <= at < request.deadline_at):
            raise TaskError("opportunity_not_current", "delivery is outside its original opportunity")
        preferences = self._policy(request.context, data["purpose"], at,
                                   token=data["preference_token"], contact_id=row["contact_id"])
        self._continuity(request.context, data.get("history"), data.get("interaction"), data.get("automatic_origin"), at,
                         last_reply=data.get("last_reply"))
        presentation = text_policy(data.get("presentation_settings") or {})
        if presentation.forbidden_word_guard(row["body"], scope_kind=request.context.scope.kind.value) is not None:
            raise TaskError("forbidden_word_blocked", "contact contains a configured forbidden word")
        if self._duplicate(request.context, row["body"], preferences, at,
                purpose=data["purpose"], contact_id=row["contact_id"], origin=data.get("automatic_origin")):
            raise TaskError("contact_duplicate", "another confirmed or unresolved contact already uses this text")
        # Delivery re-reads the sealed plan only. It never re-decides presentation,
        # so a restart sends exactly what the original decision sealed.
        reaction = data.get("reaction")
        if reaction is None:
            if voice is None and poke is None:
                return row["body"]
            return DeliveryContent(row["body"], (), voice=voice, poke=poke)
        if not self._reaction_available(request.context, row["contact_id"]):
            raise TaskError("reaction_unavailable", "selected proactive reaction is no longer allowed")
        image = self.semantics.reactions.contact_image(request.context, row["contact_id"], reaction,
            datetime.fromisoformat(reaction["issued_at"]), evidence=tuple(source_from_document(ref) for ref in data["sources"]))
        if image_manifest(image) != reaction["manifest"]:
            raise TaskError("reaction_changed", "selected proactive reaction no longer matches its original")
        return DeliveryContent(row["body"], (image,), voice=voice, poke=poke)

    def _draft(self, request, at):
        require(self.tasks.authorize_context(request.context, action=GROUP, observed_at=at))
        row = self.runtime.read_one("SELECT * FROM proactive_contacts WHERE contact_id = ?", (request.source_ref,))
        if (row is None or request.owner != GROUP or request.logical_key != row["contact_id"]
                or row["origin_key"] != request.context.key or request.payload_hash != row["payload_hash"]):
            raise TaskError("contact_draft_unavailable", "delivery must retain its original contact draft and authority")
        data = json.loads(row["record_json"])
        try:
            # A damaged presentation plan is an unavailable draft, never a silent
            # downgrade to text: the recipient either gets the sealed plan or nothing.
            voice, poke = VoicePlan.parse(data.get("voice")), PokePlan.parse(data.get("poke"))
        except ValueError as error:
            raise TaskError("contact_draft_unavailable", "original contact voice or poke plan changed") from error
        reaction = data.get("reaction")
        if ((reaction is not None and (not isinstance(reaction, dict) or not isinstance(reaction.get("manifest"), dict)))
                or manifest_hash(row["body"], (reaction["manifest"],) if reaction else ()) != row["payload_hash"]):
            raise TaskError("contact_draft_unavailable", "original contact image manifest or body changed")
        if data["decision"] != "send":
            raise TaskError("contact_not_selected", "a skipped contact has no deliverable body")
        operation = require(self.operations.get(row["operation_id"]))
        if operation.state is not OperationState.COMPLETED:
            raise TaskError("contact_draft_unavailable", "draft publication has no completed local receipt")
        self._records(request.context, tuple(source_from_document(ref) for ref in data["sources"]), at,
                      hashes=tuple(data["source_hashes"]))
        if data.get("last_reply") is not None:
            if self.history is None:
                raise TaskError("delivery_history_unavailable", "contact requires its original reply history")
            self.history.verify_reply(data["last_reply"], request.context, at)
        return row, data, voice, poke

    @outcome
    def history_text(self, request, at):
        row, data, _, _ = self._draft(request, at)
        # Pauses and expired opportunities govern future sends, not the truth of
        # a past receipt. Revoked evidence and its historical ancestry still apply.
        history = data.get("history")
        reaction = data.get("reaction")
        return HistoricalText(row["body"], tuple(history["references"]) if history else (),
                              (reaction["manifest"],) if reaction else ())

    @property
    def active_handles(self):
        return ((self.runner.active_handles if self.runner else ())
                + (self.judge_runner.active_handles if self.judge_runner else ())
                + tuple("contact-invocation-" + str(id(t)) for t in self._invocations))

    def _delivery_row(self, task_id):
        contact = self.runtime.read_one("SELECT contact_id FROM proactive_contacts WHERE task_id = ?", (task_id,))
        if contact is None:
            return None
        identifier = "outbound-" + digest([GROUP, contact["contact_id"]])
        return self.runtime.read_one("SELECT * FROM background_deliveries WHERE delivery_id = ?", (identifier,))

    @outcome
    def observe(self, context, task_id):
        """Authorized status only: a saved draft or platform acceptance is not delivery."""
        with self.runtime.read_snapshot():
            task = require(self.tasks.read(context, task_id))
            if task.spec.kind != CONTACT_KIND:
                raise TaskError("contact_task_required", "task does not belong to the contact worker")
            delivery = self._delivery_row(task_id)
            contact = self.runtime.read_one("SELECT record_json FROM proactive_contacts WHERE task_id = ?", (task_id,))
            data = json.loads(contact["record_json"]) if contact is not None else {}
            judge = data.get("judge") or {}
            return {"task_id": task_id, "revision": task.revision, "generation": task.state,
                "skipped": data.get("decision") == "skip", "dedup_reason": data.get("dedup_reason"),
                "judge": judge.get("state"), "judge_allowed": judge.get("allowed"),
                "judge_reason": judge.get("failure") or judge.get("reason"),
                "delivery_id": delivery["delivery_id"] if delivery else None,
                "delivery": delivery["state"] if delivery else None,
                "receipt_ref": delivery["receipt_ref"] if delivery else None}

    @outcome
    def cancel(self, context, task_id, *, expected_revision):
        self.require_running()
        with self.runtime.transaction():
            task = require(self.tasks.read(context, task_id))
            if task.spec.kind != CONTACT_KIND:
                raise TaskError("contact_task_required", "task does not belong to the contact worker")
            require(self.tasks.cancel(context, task_id, expected_revision=expected_revision))
            delivery = self._delivery_row(task_id)
            if delivery is not None:
                sending = require(self.tasks.read(context, delivery["task_id"]))
                require(self.tasks.cancel(context, sending.task_id, expected_revision=sending.revision))
                self.delivery.settle()
        self.notify()
        return require(self.observe(context, task_id))

    def cancel_running(self):
        for task in tuple(self._invocations):
            task.cancel()

    async def close(self):
        self._closed = True
        self.cancel_running()
        if self.runner is not None:
            await self.runner.close()
        if self.judge_runner is not None:
            await self.judge_runner.close()
        if self._invocations:
            await asyncio.wait(tuple(self._invocations), timeout=0.25)
