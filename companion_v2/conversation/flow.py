"""Durable debounce and ordered conversation progress, driven by the host lifecycle.

Only flows admitted here are scheduled. Historical manually created batches are
never enrolled implicitly. This owner does no model, tool or platform I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
import math

from companion_v2.execution.models import QUEUED, TERMINAL, TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import ScopeKind
from .busy_gate import deadline_for_deferral, validate_defer_seconds
from .group_timing import short_input_wait
from .segmentation import part_gap_seconds
from .media.models import fits_budget
from .media.codec import image_descriptor
from .media.audio.models import AudioDescriptor, fits_audio_budget
from .media.video.models import VideoDescriptor, fits_video_budget
from .quotes.models import event_images, event_forwards
from .forwards.models import ForwardDescriptor, fits_forwards


ACTIVE = "('collecting', 'generating', 'delivering')"
# Both open reasons extend the same first window: a busy deferral is a debounce
# that starts later, so a newer message still joins the very same batch.
COLLECTING_REASONS = ("debounce", "busy_delay")


@dataclass(frozen=True)
class ConversationPolicy:
    quiet_seconds: float = 0.6
    maximum_wait_seconds: float = 2
    turn_timeout_seconds: float = 180
    part_gap_seconds: float = 1.5
    # A busy-hour deferral is added to this first window only. Keeping it at the
    # end with a default leaves every existing positional construction valid.
    defer_seconds: float = 0.0

    def __post_init__(self):
        for name, minimum, maximum in (
            ("quiet_seconds", 0, 10), ("maximum_wait_seconds", 0, 30),
            ("turn_timeout_seconds", 1, 3600), ("part_gap_seconds", 0, 60),
            ("defer_seconds", 0, 900),
        ):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError("conversation timing must be finite and bounded")
        if not self.quiet_seconds <= self.maximum_wait_seconds < self.turn_timeout_seconds:
            raise ValueError("debounce must fit inside the original turn deadline")


@dataclass(frozen=True)
class FlowWork:
    batch_id: str
    context: TaskContext
    task_id: str


class ConversationFlow:
    def __init__(self, messages, delivery, *, policy=ConversationPolicy()):
        if delivery.messages is not messages or not isinstance(policy, ConversationPolicy):
            raise ValueError("flow must use the original message and delivery owners")
        self.messages, self.delivery, self.policy = messages, delivery, policy
        self.tasks, self.runtime = messages.tasks, messages.runtime

    def row(self, batch_id):
        row = self.runtime.read_one("SELECT * FROM conversation_flows WHERE batch_id = ?", (batch_id,))
        if row is None:
            raise TaskError("conversation_unmanaged", "this batch has no automatic scheduling ownership")
        return row

    @outcome
    def accept(self, context, event, *, role_instruction, defer_seconds=0.0):
        defer = validate_defer_seconds(defer_seconds)
        with self.runtime.transaction() as connection:
            self.messages.authorize(context)
            prior = connection.execute("SELECT batch_id FROM conversation_inputs WHERE event_key = ?", (event.scoped_key,)).fetchone()
            if prior:
                batch_id = require(self.messages.accept(context, event, role_instruction=role_instruction))
                self.row(batch_id)
                return batch_id  # Replays cannot extend the debounce or revive a completed flow.
            now = self.tasks.now()
            merge_key = digest([context.key, role_instruction])
            tail = connection.execute("""SELECT f.*, b.state AS batch_state FROM conversation_flows f
                JOIN conversation_batches b ON b.batch_id = f.batch_id
                WHERE f.route_key = ? ORDER BY f.sequence DESC LIMIT 1""", (context.scope.key,)).fetchone()
            batch_id = None
            if (tail and tail["merge_key"] == merge_key and tail["state"] == "collecting"
                    and tail["reason"] in COLLECTING_REASONS
                    and tail["batch_state"] == "open" and stamp(now) < tail["due_at"]):
                count = connection.execute("SELECT COUNT(*) FROM conversation_inputs WHERE batch_id = ?", (tail["batch_id"],)).fetchone()[0]
                images = list(event_images(event))
                audios = list(getattr(event, "audios", ()))
                videos = list(getattr(event, "videos", ()))
                forwards = list(event_forwards(event))
                for item in connection.execute("SELECT event_json FROM conversation_inputs WHERE batch_id = ? AND withdrawn = 0", (tail["batch_id"],)):
                    document = json.loads(item["event_json"])
                    audios.extend(AudioDescriptor(**a) for a in document.get("audios", ()))
                    videos.extend(VideoDescriptor.restore(v) for v in document.get("videos", ()))
                    previous = [*document.get("images", []), *(i for q in document.get("quotes", []) for i in q["images"])]
                    prior_forwards = [*document.get("forwards", []),
                                      *(f for q in document.get("quotes", []) for f in q.get("forwards", []))]
                    previous.extend(i for f in prior_forwards for n in f["nodes"] for i in n["images"])
                    images.extend(image_descriptor(item) for item in previous)
                    forwards.extend(ForwardDescriptor.restore(f) for f in prior_forwards)
                if count < 32 and fits_budget(images) and fits_forwards(forwards) and fits_audio_budget(audios, images) and fits_video_budget(videos, images, audios):
                    batch_id = tail["batch_id"]
            batch_id = require(self.messages.accept(context, event, role_instruction=role_instruction, batch_id=batch_id))
            if tail and batch_id == tail["batch_id"]:
                policy = ConversationPolicy(**json.loads(tail["policy_json"]))
                previous_due = datetime.fromisoformat(tail["due_at"])
                deadline = datetime.fromisoformat(tail["deadline_at"])
                due = min(datetime.fromisoformat(tail["merge_until"]), now + timedelta(seconds=policy.quiet_seconds),
                          deadline)
                if count + 1 == 32:
                    due = now
                reason = tail["reason"]
                if defer > 0:
                    # A busy deferral belongs to the batch: the newest message keeps
                    # the wait and may extend it, never shorten it. The deadline is
                    # pushed out to cover the delay, bounded by the gate's maximum.
                    due = min(now + timedelta(seconds=policy.quiet_seconds + defer), deadline)
                    deadline = max(deadline, deadline_for_deferral(
                        now=now, due_at=due, deadline_at=now + timedelta(seconds=policy.turn_timeout_seconds),
                        turn_timeout_seconds=policy.turn_timeout_seconds,
                        quiet_seconds=policy.quiet_seconds, max_delay_seconds=defer))
                    reason = "busy_delay"
                if count + 1 == 32:
                    due = now  # The batch is full: seal it instead of debouncing again.
                else:
                    # A batch that is already waiting keeps waiting: no input pulls
                    # its own promise forward, and none pushes ``due_at`` past the
                    # deadline that would otherwise discard the whole batch.
                    due = max(previous_due, min(due, deadline))
                connection.execute("UPDATE conversation_flows SET due_at = ?, deadline_at = ?, reason = ? WHERE batch_id = ?",
                                   (stamp(due), stamp(deadline), reason, batch_id))
            else:
                policy, initial_wait = self.policy, self.policy.quiet_seconds
                if context.scope.kind is ScopeKind.GROUP and self.messages.reply_settings is not None:
                    values = self.messages.reply_settings.capture(context, now)["settings"]
                    source = self.messages._read_source(event.source, context, event.capability, now)
                    initial_wait = max(initial_wait, min(short_input_wait(event, source.payload, values),
                                                        policy.turn_timeout_seconds - 0.001))
                    policy = replace(policy, maximum_wait_seconds=max(policy.maximum_wait_seconds, initial_wait))
                # A busy deferral moves the first window, and only as far as keeps
                # one further quiet window inside the original turn deadline. The
                # extension is bounded by the gate's own maximum, never unbounded.
                due_at = now + timedelta(seconds=initial_wait + defer)
                deadline_at = deadline_for_deferral(
                    now=now, due_at=due_at, deadline_at=now + timedelta(seconds=policy.turn_timeout_seconds),
                    turn_timeout_seconds=policy.turn_timeout_seconds,
                    quiet_seconds=policy.quiet_seconds, max_delay_seconds=defer)
                connection.execute("""INSERT INTO conversation_flows
                    (batch_id, route_key, merge_key, state, due_at, merge_until, deadline_at, policy_json, reason)
                    VALUES (?, ?, ?, 'collecting', ?, ?, ?, ?, ?)""",
                    (batch_id, context.scope.key, merge_key, stamp(due_at),
                     stamp(now + timedelta(seconds=policy.maximum_wait_seconds)),
                     stamp(deadline_at), encode(policy), "busy_delay" if defer > 0 else "debounce"))
            return batch_id

    def _update(self, batch_id, *, state, due_at=None, reason=""):
        with self.runtime.transaction() as connection:
            require(self.tasks.check_generation())
            connection.execute("""UPDATE conversation_flows SET state = ?, due_at = COALESCE(?, due_at),
                reason = ? WHERE batch_id = ?""", (state, stamp(due_at) if due_at else None, reason, batch_id))

    def halt(self, batch_id, reason, *, closed=False):
        """Trusted owner cleanup; only unstarted queue entries can be discarded."""
        with self.runtime.transaction():
            require(self.tasks.check_generation())
            self._update(batch_id, state="closed" if closed else "blocked", reason=reason)
            batch = self.messages.batch(batch_id)
            ids = ([batch["generation_task_id"]] if batch["generation_task_id"] else [])
            ids += [r["task_id"] for r in self.runtime.read_all(
                "SELECT task_id FROM conversation_parts WHERE batch_id = ? AND task_id IS NOT NULL", (batch_id,))]
            for task_id in ids:
                require(self.tasks.discard_queued(task_id, reason="owner_closed" if closed else "owner_unavailable"))

    @outcome
    def cancel(self, context, batch_id):
        with self.runtime.transaction():
            self.row(batch_id)
            require(self.messages.cancel(context, batch_id))
            self.halt(batch_id, "cancelled", closed=True)
            return batch_id

    def _heads(self, excluded):
        exclusions = "" if not excluded else " AND f.batch_id NOT IN (" + ",".join("?" for _ in excluded) + ")"
        return (f"""FROM conversation_flows f WHERE f.state IN {ACTIVE}
            AND NOT EXISTS (SELECT 1 FROM conversation_flows previous
                WHERE previous.route_key = f.route_key AND previous.sequence < f.sequence
                AND previous.state IN {ACTIVE})""" + exclusions, tuple(excluded))

    def next_wake(self, *, excluded=()):
        sql, args = self._heads(excluded)
        row = self.runtime.read_one("SELECT MIN(MIN(f.due_at, f.deadline_at)) AS next_at " + sql, args)
        return datetime.fromisoformat(row["next_at"]) if row["next_at"] else None

    @outcome
    def advance(self, *, limit=32, excluded=()):
        if type(limit) is not int or not 1 <= limit <= 32 or len(excluded) > 32:
            raise ValueError("flow scans must be bounded")
        require(self.tasks.check_generation())
        sql, args = self._heads(excluded)
        due = self.runtime.read_all("SELECT f.batch_id " + sql +
            " AND MIN(f.due_at, f.deadline_at) <= ? ORDER BY f.due_at, f.sequence LIMIT ?",
            args + (stamp(self.tasks.now()), limit))
        work = []
        for candidate in due:
            batch_id = candidate["batch_id"]
            try:
                # A failing admission rolls back seal/part assignment before its status is saved.
                with self.runtime.transaction():
                    item = self._advance_one(batch_id)
                    if item:
                        work.append(item)
            except TaskError as error:
                if error.code in ("supervisor_generation_conflict", "supervisor_fenced"):
                    raise
                if error.code == "task_queue_full":
                    self.defer(batch_id)
                else:
                    self.halt(batch_id, error.code)
        return tuple(work)

    def defer(self, batch_id):
        with self.runtime.transaction():
            row = self.row(batch_id)
            self._update(batch_id, state=row["state"], due_at=min(datetime.fromisoformat(row["deadline_at"]),
                         self.tasks.now() + timedelta(seconds=0.25)), reason="capacity_wait")

    def completed(self, batch_id, result):
        with self.runtime.transaction():
            require(self.tasks.check_generation())
            if result.failure:
                self.halt(batch_id, result.failure.code)
            elif result.unwrap().task is None or result.unwrap().task.state in QUEUED:
                self.defer(batch_id)
            else:
                row = self.row(batch_id)
                if row["state"] in ("collecting", "generating", "delivering"):
                    self._update(batch_id, state=row["state"], due_at=self.tasks.now())

    def _dispatch(self, row, context, task):
        if task.state in QUEUED:
            self.defer(row["batch_id"])
            return FlowWork(row["batch_id"], context, task.task_id)
        if task.state in TERMINAL:
            raise TaskError("conversation_task_" + task.state, "original task cannot be automatically replayed")
        # Only another trusted worker could own it; do not duplicate its handle.
        self._update(row["batch_id"], state=row["state"], due_at=task.spec.deadline_at, reason="worker_pending")

    def _advance_one(self, batch_id):
        row = self.row(batch_id)
        batch = self.messages.batch(batch_id)
        if row["state"] not in ("collecting", "generating", "delivering"):
            return None
        if batch["state"] in ("cancelled", "invalidated"):
            self.halt(batch_id, batch["state"], closed=True)
            return None
        context = TaskContext.restore(json.loads(batch["context_json"]))
        self.messages.authorize(context)
        participation = getattr(self.messages.tools, "group_participation", None)
        if participation is not None and participation.finish_if_skipped(context, batch_id):
            return None
        now = self.tasks.now()
        deadline = datetime.fromisoformat(row["deadline_at"])
        if now >= deadline:
            require(self.messages.cancel(context, batch_id))
            self.halt(batch_id, "deadline_elapsed", closed=True)
            return None
        if row["state"] == "collecting":
            task = require(self.messages.seal(context, batch_id, deadline_at=deadline))
            captured = json.loads(self.messages.batch(batch_id)["contributions_json"]).get("reply_settings")
            if captured is not None:
                policy = replace(ConversationPolicy(**json.loads(row["policy_json"])),
                                 part_gap_seconds=captured["settings"]["part_gap_ms"] / 1000)
                with self.runtime.transaction() as connection:
                    connection.execute("UPDATE conversation_flows SET policy_json = ? WHERE batch_id = ?", (encode(policy), batch_id))
            self._update(batch_id, state="generating", due_at=now)
            return self._dispatch(self.row(batch_id), context, task)
        generation = require(self.tasks.read(context, batch["generation_task_id"]))
        if generation.state != "succeeded":
            return self._dispatch(row, context, generation)
        self._update(batch_id, state="delivering")
        parts = self.runtime.read_all("SELECT * FROM conversation_parts WHERE batch_id = ? ORDER BY sequence", (batch_id,))
        captured = json.loads(batch["contributions_json"]).get("reply_settings")
        reply_settings = captured.get("settings", {}) if isinstance(captured, dict) else {}
        previous_at = None
        previous_text = ""
        for part in parts:
            if part["state"] == "delivered":
                if require(self.tasks.read(context, part["task_id"])).state != "succeeded":
                    raise TaskError("message_delivery_unresolved", "receipt requires reconciliation with a stopped original task")
                previous_at = datetime.fromisoformat(part["delivered_at"])
                previous_text = part["text"]
                continue
            if part["state"] != "pending":
                raise TaskError("message_delivery_unresolved", "original dispatch needs an explicit receipt reconciliation")
            # A group image may not leave before its safety review is decided. The
            # batch keeps its place in the route and is reconsidered on the next
            # bounded poll, while the review runs as its own background task.
            if part["task_id"] is None and self.delivery.pending_review(part):
                self._update(batch_id, state="delivering",
                             due_at=min(deadline, now + timedelta(seconds=self.policy.quiet_seconds)),
                             reason="image_review_pending")
                return None
            if part["task_id"]:
                task = require(self.tasks.read(context, part["task_id"]))
                due_at = task.spec.not_before
            else:
                policy = ConversationPolicy(**json.loads(row["policy_json"]))
                gap = (part_gap_seconds(reply_settings, previous_text,
                                        f"{batch_id}:{part['part_id']}")
                       if previous_at and reply_settings else policy.part_gap_seconds)
                due_at = max(now, previous_at + timedelta(seconds=gap)) if previous_at else now
                if due_at >= deadline:
                    raise TaskError("conversation_delivery_deadline", "remaining part spacing exceeds the original deadline")
                task = require(self.delivery.queue_next(context, batch_id, deadline_at=deadline, not_before=due_at)).task
            if due_at > now:
                self._update(batch_id, state="delivering", due_at=due_at, reason="part_spacing")
                return None
            return self._dispatch(self.row(batch_id), context, task)
        self._update(batch_id, state="complete", reason="confirmed_delivery")
        return None

    @outcome
    def reconcile_delivery(self, context, part_id):
        """Explicit receipt adoption can resume only a flow stopped on delivery uncertainty."""
        with self.runtime.transaction():
            part = self.delivery._part(part_id)
            row = self.row(part["batch_id"])
            task = require(self.delivery.reconcile_task(context, part_id))
            if (task.state == "succeeded" and row["state"] == "blocked"
                    and row["reason"] == "message_delivery_unresolved"):
                newer = self.runtime.read_one("SELECT 1 FROM conversation_flows WHERE route_key = ? AND sequence > ? LIMIT 1",
                                              (row["route_key"], row["sequence"]))
                if newer:
                    require(self.messages.cancel(context, row["batch_id"]))
                    self.halt(row["batch_id"], "newer_input_received", closed=True)
                else:
                    self._update(row["batch_id"], state="delivering", due_at=self.tasks.now())
            return task

    @outcome
    def observe(self, context, batch_id):
        with self.runtime.read_snapshot():
            self.messages.owned(context, batch_id)
            row = self.row(batch_id)
            return {name: row[name] for name in ("batch_id", "state", "due_at", "deadline_at", "reason")}
