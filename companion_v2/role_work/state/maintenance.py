"""Background model maintenance on the shared supervisor, budget and host lifecycle."""

import asyncio
from datetime import datetime, timedelta
import json
import random

from companion_v2.conversation.foreground import BackgroundPromptTrigger, PromptMaterial, PromptRequest, SealedForegroundContext
from companion_v2.conversation.messages import event_from_document
from companion_v2.execution.models import (Lane, ProviderBinding, SideEffect, TaskContext, TaskDefinition,
    TaskError, TaskRegistration, TaskResult, TaskSpec, digest, encode, require, stamp)
from companion_v2.execution.runner import ExactTaskRunner
from companion_v2.execution.service import outcome
from companion_v2.model_gateway.models import ModelTaskProfile
from companion_v2.identity_policy.private_domain import source_ref
from .service import FIELDS, INSTRUCTION
from . import humanized
from . import mood
from .cycle_prompts import INSTRUCTION as CYCLE_INSTRUCTION, MAINTENANCE as CYCLE_MAINTENANCE, PHASE_HINTS

KIND = "role.state.maintain"
# The local patrol reads state once per bound role and never calls a model; the
# throttle only keeps the wake loop from re-reading configuration on every tick.
PATROL_CHECK_SECONDS = 60
PROMPT = INSTRUCTION + (
    "维护你自身此刻的连续状态，沿用已有状态，只做符合人格和当前材料的自然变化。"
    "原角色设定优先，是否有实体、需要吃睡或周期由设定解释，不用关键词判断。"
    "用户说吃了饭是用户自述；邀请你吃饭、关心你或提供建议也不证明你已执行。"
    "计划只提供意图与时间线；不能根据时间经过宣称吃饭、服药、到达、病愈或完成日程。"
    "可以自然感到饿、疲倦、恢复精神，也可以保持未知；不要每天必定生病或添加戏剧冲突。"
    "sleep 的实际睡眠执行状态以活动回执为准。busy 描述注意力，不直接决定是否拒答。"
    "同一人格的所有窗口读取同一份心情、位置、忙碌和临时状态；只写你自身的概括感受与活动，不写聊天对象、他人的位置/活动或私人日程。"
    "不要把当前窗口没有新消息理解为你已不忙、情绪归零或状态结束；没有足够依据时沿用有效状态或置空。"
    "临时影响保留合理 expires_at（含时区）；到期不是康复证明。"
    "presence 是 QQ 公开短状态，最多 8 个字符，只写自己的泛化活动，如阅读中或休息中；不含用户隐私。"
    "online_mode 是可选的普通 QQ 在线模式：online、away、busy、invisible 或 null；只有当前状态确实需要改变时才选择模式，"
    "从忙碌或离开恢复时可选择 online，不确定就保留 null。它不表示是否回应用户。"
    "只输出 JSON 对象，字段为 energy（0到100或null）、hunger、health、sleep、busy、mood、location、cycle、presence、online_mode"
    "（通常为简短文字或null，cycle 也支持下述结构）、conditions（数组，元素为 kind、text、expires_at）。"
    "conditions.kind 可为 hunger、health、sleep、busy、mood、cycle、other。没有临时变化时用空数组。"
)


def _interest_level(received, characters, at):
    """Structural interest only: how much traffic arrived, never what it says."""
    if not received:
        return 0
    recent = sum(1 for moment in received if (at - moment).total_seconds() <= 1800)
    if len(received) >= 6 or characters >= 500:
        return 2
    if len(received) >= 3 or characters >= 120 or recent >= 3:
        return 1
    return 0


def _mood_defaults():
    return {"axes": False, "gate": "closed", "interest": 0, "messages": 0, "characters": 0,
            "reference": {name: float(mood.DEFAULT_BASELINE) for name in mood.AXES},
            "allowed": {name: [mood.MINIMUM, mood.MAXIMUM] for name in mood.AXES},
            "baseline": mood.DEFAULT_BASELINE, "materials": (), "sources": ()}


def _skills_instruction(*, refs, partial):
    """Let confirmed skills shape the activities, without inventing progress.

    The records are a reference for what this role can plausibly be doing; they are
    not a task list, and nothing in them licenses a claim of improvement. A partial
    selection is stated so an omitted skill is not read as an absent one.
    """
    if not refs:
        return "\n本轮没有可用的角色技能资料：只依据其他材料安排活动，不要凭空假定角色擅长什么。"
    note = ("（本轮技能资料有条目上限，未列出的技能同样可能存在，不代表角色不会。）" if partial else "")
    return ("\n安排活动时参考上面已确认的角色技能与长期目标：优先选择与当前技能相称、"
            "或与活跃目标相关的活动，避免安排明显超出或完全用不上的活动。"
            "技能资料只是能力参考，不是本轮任务清单；不要为了贴合技能而虚构练习成果，"
            "也不要把定性进展写成等级、分数或熟练度数值。" + note)
def _mood_instruction(*, enabled, axes, gate, reference, allowed, baseline, interest, half_life, band, cross_window):
    """Per-round mood output contract; the model still authors every number."""
    if not enabled:
        return "mood 输出简短文字或 null，不使用结构对象。"
    lead = ("mood 沿用上一轮的结构：baseline、joy、anger、sorrow、fear、intensity（mild、moderate、strong 或 null）、description。"
            "情绪随时间与无交互自然回归基线：一次夸奖不让你整日亢奋，一次不愉快不让你永久低落；"
            "数值只是语气与浓度，不覆盖原人格、当前事实和你的判断，也不改变是否回应。"
            "description 只写你自己的主观感受，不诊断用户心情，也不把负面情绪归咎于用户。" if axes else
            "mood 本轮首次给出结构对象：baseline、joy、anger、sorrow、fear（各 1 到 10 的整数）、"
            "intensity（mild、moderate、strong 或 null）、description（你自己的主观感受，只写自己）；"
            "上一轮只有文字时把它的意思并入 description，保持连续。")
    return lead + (mood.prompts.maintenance(reference=reference, allowed=allowed, baseline=baseline,
        half_life_minutes=half_life, interest_level=interest, neutral_band=band, cross_window=cross_window) if gate == "open"
        else "本轮不做情绪数值更新：保持上一轮各轴数值不变，只按当前材料更新 description。")


def state_profile(provider, *, max_output_tokens=1024):
    return ModelTaskProfile(KIND, Lane.BACKGROUND, provider, "保持原人格，维护自己的生活状态。",
                            max_output_tokens=max_output_tokens)


class StateMaintenance:
    def __init__(self, runtime):
        self.runtime = runtime
        self.pending, self.committed, self.workers, self.results = {}, set(), {}, {}
        self.closed = False
        self.bindings = {}
        self.patrol_results = {}
        self._patrol_checked_at = None
        self._scan_after = None
        self.registrations = (TaskRegistration(TaskDefinition(KIND, "role.state", KIND, Lane.BACKGROUND,
            side_effect=SideEffect.LOCAL, binding=ProviderBinding("role.state", "local", "1", "state-1"),
            timeout_seconds=180, max_attempts=1, concurrency=1), self.validate),)

    def attach(self, app):
        self.app, self.service, self.tasks, self.gateway = app, app.role_state, app.tasks, app.gateway
        self.runner = ExactTaskRunner(self.tasks, frozenset({KIND}), self.generate, waiting=app.background_waiting)

    def bind(self, context, instruction, *, guard=None):
        old = self.bindings.get(context.key)
        self.bindings[context.key] = (context, instruction, guard or (old[2] if old else None))
        settings, token = self.service.settings(context)
        row = self.runtime.read_one("SELECT * FROM role_state_schedules WHERE context_key = ?", (context.key,))
        if row is None and not settings["enabled"]:
            return
        values = {"values": settings, "token": token, "instruction": instruction}
        encoded = encode(values)
        if row and row["settings_json"] == encoded:
            return
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO role_state_schedules VALUES (?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(context_key) DO UPDATE SET context_json=excluded.context_json,
                settings_json=excluded.settings_json, next_at=excluded.next_at,
                revision=excluded.revision, enabled=excluded.enabled""",
                (context.key, encode(context), encoded, stamp(self.tasks.now()),
                 row["revision"] + 1 if row else 1, int(settings["enabled"])))

    def foreground_busy(self, context):
        return self.runtime.read_one("""SELECT 1 FROM conversation_flows f JOIN conversation_batches b USING(batch_id)
            WHERE f.state IN ('collecting','generating','delivering')
              AND json_extract(b.context_json, '$.role_binding.scope.installation_id') = ?
              AND json_extract(b.context_json, '$.role_binding.scope.bot_id') = ?
              AND json_extract(b.context_json, '$.role_binding.role.subject_id') = ? LIMIT 1""",
            (context.scope.installation_id, context.scope.bot_id, context.role_binding.role.subject_id)) is not None

    def _events(self, context):
        """Current observed inputs: the recent four for the prompt, more for interest."""
        rows = self.runtime.read_all("""SELECT i.event_json FROM conversation_inputs i
            JOIN conversation_batches b USING(batch_id) JOIN conversation_flows f USING(batch_id)
            WHERE b.origin_key = ? AND i.withdrawn = 0 ORDER BY f.sequence DESC, i.position DESC LIMIT 4""", (context.key,))
        return tuple(event_from_document(json.loads(row["event_json"]), context) for row in reversed(rows))

    def _inputs(self, context, events):
        materials, sources = [], []
        for event in events:
            try:
                source = self.app.messages._read_source(event.source, context, event.capability, self.tasks.now())
            except TaskError:
                continue
            materials.append(PromptMaterial(event.source.owner, "reported_conversation", source.payload[:4096], event.source))
            sources.append(event.source)
        return tuple(materials), tuple(sources)

    def _skills(self, context, at):
        """The role's confirmed skills, so its activities can match what it can do.

        Optional in both directions: a window without ``role.growth.read`` or without
        a settled private audience contributes nothing rather than failing, and the
        material carries no source because a growth record is a confirmed subjective
        record, not observed evidence. Only ACTIVE and PAUSED records arrive, and the
        reader has already rechecked scope, audience and every supporting source.
        """
        reader = getattr(self.app, "role_growth_context", None)
        if reader is None:
            return (), (), False
        try:
            candidates = reader.reader.candidates(context, at)
        except (TaskError, KeyError, ValueError):
            return (), (), False
        materials = tuple(PromptMaterial("role.growth", item.purpose, item.payload)
                          for item in candidates.items)
        references = tuple(item.reference for item in candidates.items)
        return materials, references, candidates.truncated or bool(candidates.skipped)

    def _skills_changed(self, job, context, at):
        """Whether the skill material a job was prepared from has since moved."""
        _, references, _ = self._skills(context, at)
        return references != job["growth_refs"]

    def _mood(self, context, events, settings, record, at):
        """One bounded mood round: structural interest, decay reference, then a probability gate.

        The gate only decides whether the numbers may move. Relaxation still appears in the
        decay reference, and a held round keeps the previous axes as they were.
        """
        if not settings["mood_enabled"]:
            return dict(_mood_defaults())
        stored = record["values"]["mood"] if record else None
        dynamics = record.get("mood_dynamics") if record else None
        previous = mood.previous_axes(stored, dynamics)
        baseline = mood.baseline_of(stored, dynamics)
        rows = self.runtime.read_all("""SELECT i.event_json FROM conversation_inputs i
            JOIN conversation_batches b USING(batch_id)
            WHERE b.origin_key = ? AND i.withdrawn = 0 AND json_extract(i.event_json, '$.received_at') > ?
            ORDER BY json_extract(i.event_json, '$.received_at') DESC LIMIT 32""",
            (context.key, stamp(at - timedelta(minutes=settings["mood_interest_window_minutes"]))))
        recent, characters, materials, sources = [], 0, [], []
        for row in reversed(rows):
            event = event_from_document(json.loads(row["event_json"]), context)
            try:
                source = self.app.messages._read_source(event.source, context, event.capability, self.tasks.now())
            except TaskError:
                continue
            recent.append(event.received_at)
            characters += len(source.payload)
            if len(materials) < 4:
                materials.append(PromptMaterial(event.source.owner, "reported_conversation", source.payload[:4096], event.source))
                sources.append(event.source)
        interest = _interest_level(recent, characters, at)
        hint = mood.bounds(previous, at=at, half_life_minutes=settings["mood_decay_half_life_minutes"],
                           max_delta=settings["mood_update_max_delta"])
        # A body that has never carried numbers, or whose axes can no longer be read, must
        # be free to establish them; otherwise one unresolved round would pin it forever.
        # A configured probability of zero never opens a later round, so tests and operators
        # can hold the numbers without depending on a random draw.
        probability = settings["mood_update_probability"]
        if previous is None or probability >= 1:
            gate = "open"
        elif probability <= 0:
            gate = "hold"
        else:
            gate = "open" if random.random() < probability else "hold"
        return {"axes": previous is not None, "gate": gate, "interest": interest, "messages": len(rows),
                "characters": characters, "reference": hint["reference"], "allowed": hint["allowed"],
                "baseline": baseline, "materials": tuple(materials), "sources": tuple(sources)}

    def _calendar(self, context, at):
        try:
            return self.app.calendar.occurrences(context, start=at, end=at + timedelta(hours=24))
        except TaskError:
            return {"state": "unavailable"}

    def prepare(self, context, instruction, request_id):
        self.app.require_running()
        self.service.access.check(context, KIND)
        settings, token = self.service.settings(context)
        if not settings["enabled"]:
            raise TaskError("role_state_disabled", "maintenance is disabled")
        now = self.tasks.now()
        record = self.service.records.get(context, "current")
        events = self._events(context)
        self.service.access.check(context, "role.state.read")
        try:
            previous = self.service.read(context)
        except TaskError:
            previous = {"state": "unavailable", "revision": record["revision"] if record else 0}
        materials, sources = self._inputs(context, events)
        mood_round = self._mood(context, events, settings, record, now)
        materials = materials + mood_round["materials"]
        # Skills steer which activities the role picks, so the confirmed records ride
        # along with the material the round is authored from.
        skill_materials, growth_refs, skills_partial = self._skills(context, now)
        materials = materials + skill_materials
        calendar, activities = self._calendar(context, now), self.service.activity_context(context)
        dependencies = list(record["sources"]) if record and previous["state"] != "unavailable" and self.service.evidence.visible(context, record["sources"]) else []
        cycle_timeline, cycle_sources = self.service.cycles.preview(context, settings, now)
        dependencies.extend(json.loads(encode(cycle_sources)))
        for item in calendar.get("items", []) + activities["items"]:
            dependencies.extend(item.get("sources", []))
        sources = tuple(dict.fromkeys((*sources, *(source_ref(s) for s in mood_round["sources"]),
                                       *(source_ref(s) for s in dependencies))))
        self.service.evidence.validate(context, sources)
        return {"context": context, "instruction": instruction, "request_id": request_id, "at": now,
            "revision": record["revision"] if record else 0, "record_hash": digest(record), "previous": previous,
            "settings": settings, "token": token, "sources": sources, "materials": materials,
            "calendar": calendar, "activities": activities, "cycle_timeline": cycle_timeline,
            "mood_round": mood_round, "sleep_execution": self.service.body_clock.read(context),
            "growth_refs": growth_refs, "skills_partial": skills_partial}

    @outcome
    def validate(self, spec, at):
        self.app.require_running()
        job = self.pending.get(spec.task_id)
        if job is None or job["context"] != spec.context or digest(job) != spec.request_ref:
            raise TaskError("state_job_unavailable", "original maintenance input is unavailable")
        self.service.access.check(spec.context, KIND, at=at)
        settings, token = self.service.settings(spec.context)
        if not settings["enabled"] or token != job["token"]:
            raise TaskError("state_settings_changed", "state configuration changed")
        self.service.evidence.validate(spec.context, job["sources"], at=at)
        binding = self.bindings.get(spec.context.key)
        if binding is None or binding[1] != job["instruction"]:
            raise TaskError("state_binding_changed", "original persona is no longer bound")
        if spec.task_id not in self.committed:
            record = self.service.records.get(spec.context, "current")
            if (record["revision"] if record else 0) != job["revision"] or digest(record) != job["record_hash"]:
                raise TaskError("state_changed", "state changed during maintenance")
            if self._calendar(spec.context, job["at"]) != job["calendar"] or self.service.activity_context(spec.context) != job["activities"]:
                raise TaskError("state_material_changed", "calendar or actual activity changed during maintenance")
            if self.service.body_clock.read(spec.context) != job["sleep_execution"]:
                raise TaskError("state_material_changed", "physical sleep changed in another window")
            if self._skills_changed(job, spec.context, at):
                raise TaskError("state_material_changed", "the role's skills changed during maintenance")
        return True

    async def run(self, context, instruction, request_id):
        key = "state-task-" + digest([context.key, request_id])
        if self.closed:
            raise TaskError("state_closed", "maintenance is closed")
        if self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (key,)):
            return {"task_id": key, "state": require(self.tasks.read(context, key)).state, "replayed": True}
        binding = self.bindings.get(context.key)
        if binding is None or binding[1] != instruction:
            raise TaskError("state_not_bound", "bind the current host persona before maintenance")
        if binding[2] is not None:
            await binding[2](context.scope, context.role_binding, instruction)
        job = self.prepare(context, instruction, request_id)
        self.pending[key] = job
        try:
            require(self.tasks.submit(TaskSpec(key, context, KIND, digest(job), request_id,
                job["at"], job["at"] + timedelta(seconds=180))))
            result = require(await self.runner.run(context, key))
            if result.task.state in ("created", "retry_scheduled"):
                require(self.tasks.discard_queued(key, reason="owner_unavailable"))
            task = require(self.tasks.read(context, key))
            return {"task_id": key, "state": task.state, "reason": task.reason}
        finally:
            self.pending.pop(key, None)
            self.committed.discard(key)

    async def generate(self, run):
        job = self.pending[run.task.task_id]
        context = job["context"]
        mood_round = job["mood_round"]
        materials = (PromptMaterial("role.state", "maintenance_basis", encode({
            "at": job["at"], "previous_simulation": job["previous"], "settings": job["settings"],
            "cycle_timeline": job["cycle_timeline"], "calendar_plans": job["calendar"],
            "mood_settlement": {"reference": mood_round["reference"], "baseline": mood_round["baseline"],
                "interest_level": mood_round["interest"], "messages_since_last_round": mood_round["messages"],
                "message_characters": mood_round["characters"], "numbers_may_move": mood_round["gate"] == "open"},
            "actual_activity_records": job["activities"], "sleep_execution": job["sleep_execution"]})),) + job["materials"]
        request = PromptRequest(BackgroundPromptTrigger(job["request_id"], context.actor.principal, context.scope, job["at"]),
            job["instruction"], SealedForegroundContext(materials, (), ()),
            PROMPT + (CYCLE_INSTRUCTION + CYCLE_MAINTENANCE + "".join(PHASE_HINTS.values()) if job["settings"]["cycle_enabled"]
                      else "cycle 使用 null，conditions 不添加 cycle 项。")
            + _mood_instruction(enabled=job["settings"]["mood_enabled"], axes=mood_round["axes"], gate=mood_round["gate"],
                reference=mood_round["reference"], allowed=mood_round["allowed"], baseline=mood_round["baseline"],
                interest=mood_round["interest"], half_life=job["settings"]["mood_decay_half_life_minutes"],
                band=job["settings"]["mood_neutral_band"], cross_window=job["settings"]["mood_cross_window"])
            + _skills_instruction(refs=job["growth_refs"], partial=job["skills_partial"]),
            context.role_binding, output_format="role_state")
        result = await self.gateway.generate(run, request)
        try:
            data = json.loads(result.draft.text)
            with self.runtime.transaction():
                run.validate()
                if self.foreground_busy(context):
                    raise TaskError("state_foreground_active", "defer state changes while an original reply is using them")
                run.begin_effect()
                receipt = self.service.write(context, data=data, expected_revision=job["revision"],
                    operation_key=run.task.task_id, sources=job["sources"], projected_inputs=True,
                    mood_interest=mood_round["interest"] if mood_round["gate"] == "open" else None)
                self.committed.add(run.task.task_id)
                run.record_operation(receipt["operation_id"])
            return TaskResult("succeeded", effect="committed", result_ref=digest(receipt),
                receipt_ref=receipt["operation_id"], operation_id=receipt["operation_id"])
        except BaseException:
            self.gateway.ledger.discard(result.call_id)
            raise

    def advance(self):
        if self.closed:
            return
        self.patrol()
        for key, worker in tuple(self.workers.items()):
            if worker.done():
                del self.workers[key]
                if not worker.cancelled():
                    error = worker.exception()
                    self.results[key] = {"state": "failed", "code": getattr(error, "code", "state_worker_failed")} if error else worker.result()
                    with self.runtime.transaction() as connection:
                        connection.execute("UPDATE role_state_schedules SET result_json = ? WHERE context_key = ?",
                                           (encode(self.results[key]), key))
        if self.workers:
            return
        # Seek past visited records, including retired/unbound/disabled ones.
        # A stale prefix must not permanently hide another target's due work.
        after = self._scan_after
        rows = self.runtime.read_all("""SELECT * FROM role_state_schedules
            WHERE (? IS NULL OR next_at > ? OR (next_at = ? AND context_key > ?))
            ORDER BY next_at, context_key LIMIT 16""",
            (after[0], after[0], after[0], after[1]) if after else (None, None, None, None))
        for row in rows:
            self._scan_after = (row["next_at"], row["context_key"])
            context = TaskContext.restore(json.loads(row["context_json"]))
            if context.key not in self.bindings:
                continue  # Restart requires a fresh trusted host binding, never a stored prompt alone.
            saved = json.loads(row["settings_json"])
            try:
                self.bind(context, saved["instruction"])
                self.service.access.check(context, KIND)
                settings, token = self.service.settings(context)
                if (not settings["enabled"] or token != saved["token"] or row["next_at"] > stamp(self.tasks.now())
                        or self.foreground_busy(context) or context.key in self.workers or self.workers):
                    continue
                now = self.tasks.now()
                with self.runtime.transaction() as connection:
                    updated = connection.execute("UPDATE role_state_schedules SET next_at = ? WHERE context_key = ? AND next_at = ? AND revision = ? AND enabled = 1",
                        (stamp(now + timedelta(minutes=settings["maintenance_minutes"])), context.key, row["next_at"], row["revision"]))
                    if not updated.rowcount:
                        continue
                # next_at advances before dispatch; restart never repeats an unknown model request.
                worker = asyncio.create_task(self.run(context, saved["instruction"],
                    "state-period-" + digest([context.key, row["revision"], row["next_at"]])))
                self.workers[context.key] = worker
                worker.add_done_callback(lambda done: self.app.notify())
                return
            except TaskError:
                continue
        if len(rows) < 16:
            self._scan_after = None
        else:
            self.app.notify()  # Continue the bounded sweep after yielding to other work.

    def patrol(self):
        """V1 daily-review cadence: one local, model-free pass per local day.

        It records a structured observation of the role's own projected state and
        prunes the patrol's own records by the configured retention. A missing
        grant, a malformed observation or a damaged record only lands in
        ``patrol_results``; it never blocks the maintenance queue.
        """
        now = self.tasks.now()
        if self._patrol_checked_at is not None and (now - self._patrol_checked_at).total_seconds() < PATROL_CHECK_SECONDS:
            return
        self._patrol_checked_at = now
        for context, _instruction, _guard in tuple(self.bindings.values()):
            try:
                settings, _token = self.service.settings(context)
                if not humanized.patrol_due(self.runtime, context, settings=settings, now=now):
                    continue
                self.patrol_results[context.key] = humanized.patrol(self.service, context, settings=settings, now=now)
            except TaskError as error:
                self.patrol_results[context.key] = {"state": "blocked", "code": error.code}
            except Exception:
                # A best-effort local observation must never fault the shared host
                # loop, which treats any escaped exception as a dispatch failure.
                self.patrol_results[context.key] = {"state": "failed", "code": "state_patrol_failed"}

    def cancel_running(self):
        for worker in self.workers.values():
            worker.cancel()

    @property
    def active_handles(self):
        return self.runner.active_handles + tuple("state-maintenance:" + k for k, w in self.workers.items() if not w.done())

    async def close(self):
        self.closed = True
        self.cancel_running()
        await self.runner.close()
        if self.workers:
            await asyncio.wait(tuple(self.workers.values()), timeout=0.25)
