"""Append-only reply segments produced and delivered by the original turn owner."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
import json
from logging import getLogger

from companion_v2.delivery.media import payload_hash
from companion_v2.execution.models import TaskError, digest, require, stamp
from companion_v2.foundation.refs import ScopeKind
from .foreground import GroundedDraftReviewer
from .media.reply import reply_manifest
from .reply_preparation import observed_statements, prepare_reply
from .segment_control import controlled_parts
from .segmentation import part_gap_seconds


logger = getLogger(__name__)


def stream_record(messages, batch_id):
    return messages.runtime.read_one("SELECT * FROM conversation_reply_streams WHERE batch_id = ?", (batch_id,))


def validate_stream(messages, batch, context, at, *, final=False):
    stream = stream_record(messages, batch["batch_id"])
    if stream is None or stream["state"] != "open" or stream["call_id"] != batch["call_id"]:
        raise TaskError("message_stream_closed", "only an open original stream may append or send parts")
    captured = json.loads(batch["contributions_json"]).get("reply_settings", {})
    if captured.get("settings", {}).get("streaming_mode", "buffered") != "incremental":
        raise TaskError("message_stream_unavailable", "this sealed turn did not select incremental delivery")
    generation = require(messages.tasks.read(context, batch["generation_task_id"]))
    if generation.state != "running":
        raise TaskError("message_generation_pending", "incremental delivery requires its live generation owner")
    call = messages.runtime.read_one("SELECT task_id, state FROM model_calls WHERE call_id = ?", (stream["call_id"],))
    if call is None or call["task_id"] != generation.task_id or call["state"] not in (("generated",) if final else ("dispatched", "generated")):
        raise TaskError("message_stream_changed", "stream lost its original model invocation")
    messages._request(batch, context, at)
    return stream


class StreamingReply:
    def __init__(self, messages, run, segmentation, presentation, settings, send_part):
        self.messages, self.run = messages, run
        self.policy, self.presentation = segmentation, presentation
        self.settings, self.send_part = settings, send_part
        self.call_id = None
        self.observed_call = None
        self.source = ""
        self.consumed = 0
        self.parts = []
        self.reviewer = GroundedDraftReviewer()
        self.finished = False
        self.sender = None
        self.sent_count = 0
        self.failure = asyncio.Event()

    @property
    def published(self):
        return bool(self.parts)

    def ready(self, draft):
        return (not self.finished and draft.action == "text"
                and self._boundary(draft.text[self.consumed:], len(draft.text)) is not None)

    async def generate(self, coroutine):
        model = asyncio.create_task(coroutine)
        failure = asyncio.create_task(self.failure.wait())
        try:
            done, _ = await asyncio.wait((model, failure), return_when=asyncio.FIRST_COMPLETED)
            if failure in done:
                self.sender.result()
            return await model
        finally:
            for child in (model, failure):
                if not child.done():
                    child.cancel()
            await asyncio.gather(model, failure, return_exceptions=True)

    def _boundary(self, text, total_chars=None):
        if not self.policy.enabled or len(self.parts) >= self.policy.max_segments - 1:
            return None
        candidates = []
        if self.policy.llm_controlled:
            controlled, explicit = controlled_parts(text)
            if explicit:
                first = controlled[0]
                # This offset includes the complete boundary line, which may
                # span provider chunks and must never be shown to the user.
                from .segmentation import LLM_SEGMENT_MARKER
                marker = text.find(LLM_SEGMENT_MARKER, len(first.rstrip()))
                if marker >= 0:
                    end = marker + len(LLM_SEGMENT_MARKER)
                    if end < len(text):
                        candidates.append((end, True))
        # A stream cannot know its eventual total length; the threshold stops
        # new rule boundaries once crossed, keeping committed parts immutable.
        if (len(self.source) if total_chars is None else total_chars) <= self.policy.threshold:
            candidates.extend((end, False) for end in self.policy.rule_boundaries(text)
                              if sum(not c.isspace() for c in text[:end]) >= self.policy.min_segment_chars)
        for end, explicit in sorted(set(candidates)):
            # One following character disambiguates decimal dots, repeated
            # punctuation, end anchors and split words crossing SDK chunks.
            if end >= len(text) or not text[end:].strip():
                continue
            if not explicit and sum(not c.isspace() for c in text[end:]) < self.policy.min_segment_chars:
                continue
            if self.policy.rule_mode == "words":
                words = json.loads(self.policy.split_words)
                if any(text[start:] and len(text[start:]) < len(word) and word.startswith(text[start:])
                       for word in words for start in range(max(0, end - len(word)), end)):
                    continue
                if text[end - 1] in ".…~～" and text[end] == text[end - 1]:
                    continue
            return end
        return None

    def _prepare(self, text, draft):
        originals = observed_statements(draft)
        statements = (*originals, *(text for statement in originals if text.strip() in statement))
        if self.run.task.spec.context.scope.kind is ScopeKind.GROUP and self.settings.get("enable_group_reality_promise_guard", True):
            text, _ = self.presentation.reality_promise_guard(text, statements=statements)
        if self.presentation.forbidden_word_guard(text, scope_kind=self.run.task.spec.context.scope.kind.value) is not None:
            raise TaskError("forbidden_word_blocked", "reply contains a configured forbidden word")
        try:
            return prepare_reply(text, replace(self.policy, enabled=False), self.presentation,
                                 statements=statements).parts[0]
        except ValueError as error:
            if str(error) in ("presentation removed all visible reply text", "reply contains only control tokens"):
                return None
            raise TaskError("message_parts_invalid", "stream presentation produced invalid reply text") from error

    async def observe(self, call_id, draft):
        if self.sender is not None and self.sender.done():
            self.sender.result()
        if self.finished or draft.action != "text" or getattr(draft, "images", ()):
            return False
        if self.call_id is not None and call_id != self.call_id:
            raise TaskError("message_stream_changed", "published stream cannot switch model invocation")
        if not self.published and self.observed_call != call_id:
            self.source, self.consumed = "", 0
        self.observed_call = call_id
        if not draft.text.startswith(self.source):
            raise TaskError("message_stream_changed", "reply prefix changed after publication")
        current = self.messages.request(self.run)
        if not self.reviewer.review(draft, current.context, observed_at=self.messages.tasks.now()).approved:
            raise TaskError("draft_not_grounded", "stream evidence is outside the sealed materials")
        self.source = draft.text
        if self.presentation.forbidden_word_guard(self.source,
                scope_kind=self.run.task.spec.context.scope.kind.value) is not None:
            raise TaskError("forbidden_word_blocked", "reply contains a configured forbidden word")
        while (boundary := self._boundary(self.source[self.consumed:])) is not None:
            text = self.source[self.consumed:self.consumed + boundary]
            self.consumed += boundary
            prepared = self._prepare(text, draft)
            if prepared is None:
                continue
            await self._append(call_id, prepared)
        return self.published

    async def _append(self, call_id, text, *, final=False):
        batch_id = self.run.task.spec.request_ref
        context = self.run.task.spec.context
        with self.messages.runtime.transaction() as connection:
            self.run.validate()
            batch = self.messages.batch(batch_id)
            if not self.published:
                if batch["state"] != "sealed" or batch["call_id"] is not None:
                    raise TaskError("message_manifest_exists", "original stream cannot be published twice")
                connection.execute("INSERT INTO conversation_reply_streams VALUES (?, ?, 'open', ?)",
                                   (batch_id, call_id, stamp(self.messages.tasks.now())))
                self.call_id = call_id
            else:
                validate_stream(self.messages, batch, context, self.messages.tasks.now(), final=final)
            sequence = len(self.parts) + 1
            part_id = "part-" + digest([batch_id, sequence])
            connection.execute("""INSERT INTO conversation_parts
                (part_id, batch_id, sequence, text, payload_hash, state) VALUES (?, ?, ?, ?, ?, 'pending')""",
                (part_id, batch_id, sequence, text, payload_hash(text)))
            connection.execute("""INSERT INTO conversation_voice_diagnostics
                (part_id, candidate_reason, render_state, component_order_json, text_hidden)
                VALUES (?, 'voice_disabled', 'not_applicable', '[]', 0)""", (part_id,))
            parts = (*self.parts, text)
            if sum(map(len, parts)) > 65536:
                raise TaskError("message_parts_invalid", "stream presentation exceeds the reply limit")
            connection.execute("""UPDATE conversation_batches SET state = 'ready', revision = revision + 1,
                call_id = ?, manifest_hash = ?, part_count = ?, presentation_action = 'text' WHERE batch_id = ?""",
                (call_id, reply_manifest(batch_id, call_id, parts), len(parts), batch_id))
        self.parts.append(text)
        logger.info("[CompanionV2] 流式回复分段已校验 batch=%s part=%s sequence=%d 正文=%r",
                    batch_id, part_id, sequence, text)
        if not final:
            if self.sender is None or self.sender.done():
                if self.sender is not None:
                    self.sender.result()
                self.sender = asyncio.create_task(self._send_pending(), name="companion:stream:" + batch_id)
                self.sender.add_done_callback(self._sent)

    def _sent(self, sender):
        if not sender.cancelled() and sender.exception() is not None:
            self.failure.set()

    async def _send_pending(self):
        while self.sent_count < len(self.parts):
            part_id = "part-" + digest([self.run.task.spec.request_ref, self.sent_count + 1])
            await self.send_part(self.run, part_id, self.settings)
            self.sent_count += 1

    async def finish(self, call_id, draft):
        if not self.published:
            return False
        if call_id != self.call_id or draft.action != "text" or getattr(draft, "images", ()) or not draft.text.startswith(self.source):
            raise TaskError("message_stream_changed", "final response changed its published prefix or action")
        current = self.messages.request(self.run)
        if not self.reviewer.review(draft, current.context, observed_at=self.messages.tasks.now()).approved:
            raise TaskError("draft_not_grounded", "final stream evidence is no longer authorized")
        if self.presentation.forbidden_word_guard(draft.text,
                scope_kind=self.run.task.spec.context.scope.kind.value) is not None:
            raise TaskError("forbidden_word_blocked", "reply contains a configured forbidden word")
        self.source = draft.text
        if self.sender is not None:
            await self.sender
        tail = self.source[self.consumed:]
        # Final usage has settled; close the stream after appending the tail,
        # but deliver the last part only after generation itself succeeds.
        if tail.strip():
            text = self._prepare(tail, draft)
            if text is not None:
                await self._append(call_id, text, final=True)
        with self.messages.runtime.transaction() as connection:
            self.run.validate()
            connection.execute("UPDATE conversation_reply_streams SET state = 'complete', observed_at = ? WHERE batch_id = ?",
                               (stamp(self.messages.tasks.now()), self.run.task.spec.request_ref))
        self.finished = True
        return True

    async def interrupt(self):
        if self.sender is not None:
            if not self.sender.done():
                self.sender.cancel()
            await asyncio.gather(self.sender, return_exceptions=True)
        if self.published and not self.finished:
            with self.messages.runtime.transaction() as connection:
                connection.execute("UPDATE conversation_reply_streams SET state = 'interrupted', observed_at = ? WHERE batch_id = ?",
                                   (stamp(self.messages.tasks.now()), self.run.task.spec.request_ref))


async def send_stream_part(delivery, runner, run, part_id, settings):
    run.validate()
    part = delivery._part(part_id)
    previous = delivery.runtime.read_one("""SELECT * FROM conversation_parts
        WHERE batch_id = ? AND sequence < ? ORDER BY sequence DESC LIMIT 1""", (part["batch_id"], part["sequence"]))
    due = delivery.tasks.now()
    if previous is not None:
        if previous["state"] != "delivered":
            raise TaskError("message_previous_unconfirmed", "stream stops before any unconfirmed delivery is repeated")
        gap = part_gap_seconds(settings, part["text"] or previous["text"], f"{part['batch_id']}:{part_id}")
        due = max(due, datetime.fromisoformat(previous["delivered_at"]) + timedelta(seconds=gap))
    if due >= run.task.spec.deadline_at:
        raise TaskError("conversation_delivery_deadline", "stream spacing exceeds the original deadline")
    task = require(delivery.queue_next(run.task.spec.context, part["batch_id"],
                                     deadline_at=run.task.spec.deadline_at, not_before=due)).task
    while due > delivery.tasks.now():
        await asyncio.sleep(min(0.1, (due - delivery.tasks.now()).total_seconds()))
        run.validate()
    run.validate()
    result = require(await runner.run(run.task.spec.context, task.task_id))
    if result.task is None or result.task.state != "succeeded" or delivery._part(part_id)["state"] != "delivered":
        raise TaskError("message_delivery_unresolved", "incremental reply needs a confirmed original receipt")
