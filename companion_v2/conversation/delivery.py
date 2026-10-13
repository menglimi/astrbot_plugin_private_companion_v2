"""Trusted local sender and receipt owner. No host or platform adapter is installed."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from time import perf_counter

from companion_v2.execution.models import ProviderBinding, TaskContext, TaskError, TaskRecord, TaskResult, TaskSpec, digest, encode, require, stamp
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, VersionRef, ScopeKind
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from companion_v2.delivery.models import DeliveryEnvelope, DeliveryReceipt, LocalSender
from companion_v2.delivery.media import ImageDeliveryEnvelope, image_manifest, payload_hash
from companion_v2.delivery.plan import PokePlan
from companion_v2.memory.group.access import owner_key as group_owner_key
from companion_v2.memory.group.hits import evaluate_message, persist_hits
from .media.review import ALLOW, WITHHOLD, kept_manifests
from .media.reply import reply_manifest
from .outbound_plan import first_text_sequence, outbound_plan, sealed_inputs
from .text_processing import text_policy

from .messages import ConversationMessages, DELIVERY_KIND
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryQueueResult:
    task: TaskRecord | None


class LocalConversationDelivery:
    def __init__(self, messages: ConversationMessages, sender: LocalSender):
        self.messages = messages
        self.tasks = messages.tasks
        self.runtime = messages.runtime
        self.sender = sender
        self.operations = OperationRepository(self.runtime)

    def _part(self, part_id):
        row = self.runtime.read_one("SELECT * FROM conversation_parts WHERE part_id = ?", (part_id,))
        if row is None:
            raise TaskError("message_part_unavailable", "original reply part is unavailable")
        return row

    @staticmethod
    def _sealed_images(images, image_position):
        """The ordered manifest one outgoing reply carries, in its sealed form."""
        return tuple(image_manifest(image) for image in images), image_position

    def _sealed(self, part):
        """The sealed originals, position and sealed payload hash for one part."""
        batch = self.messages.batch(part["batch_id"])
        context = TaskContext.restore(json.loads(batch["context_json"]))
        at = self.tasks.now()
        images, _reference, image_position = self.messages.reply_images.for_part(
            part, batch, context, at, with_position=True)
        sealed = payload_hash(part["text"], images, image_position=image_position)
        if sealed != part["payload_hash"]:
            raise TaskError("reply_images_changed", "outgoing image selection differs from its sealed originals")
        return batch, context, images, image_position, sealed

    def plan_for(self, part):
        """The reviewed decision for one part, or None when it was never reviewed."""
        _batch, context, images, image_position, _sealed = self._sealed(part)
        if not images:
            return None
        return self.messages.image_review.plans(
            context, (part,), images, image_position=image_position).get(part["part_id"])

    def _content(self, part):
        """The images, position and hash this part sends: text plus the images it keeps.

        A part whose image was withheld from the group keeps its sealed row, its
        batch and its manifest untouched. Only the delivery it produces changes,
        and that substitution is recorded before the send is dispatched.
        """
        _batch, _context, images, image_position, sealed = self._sealed(part)
        plan = self.plan_for(part)
        if plan is None or plan.decision == ALLOW:
            return images, image_position, sealed
        kept = kept_manifests((image_manifest(image) for image in images), drop=(plan.manifest,))
        recorded = self.messages.image_review.substitution_hash(
            part["part_id"], text=part["text"], manifests=kept, image_position=image_position)
        substituted = payload_hash(part["text"], (), image_position=image_position)
        if recorded not in (None, substituted):
            raise TaskError("image_review_changed", "reviewed delivery no longer matches its original part")
        return (), image_position, self.messages.image_review.record(
            plan, text=part["text"], manifests=kept, at=self.tasks.now())

    def outbound_plan(self, part):
        """The sealed additions this part carries, re-derived from its own batch.

        The captured settings, the sealed inputs and the sealed parts are all
        immutable once the turn is ready, so the same plan is produced when the
        reply is generated and when it is dispatched. Nothing live is read here.
        """
        batch = self.messages.batch(part["batch_id"])
        contributions = json.loads(batch["contributions_json"])
        captured = contributions.get("reply_settings")
        settings = captured["settings"] if captured is not None else {}
        rows = self.runtime.read_all("SELECT sequence, text FROM conversation_parts "
                                     "WHERE batch_id = ? ORDER BY sequence", (part["batch_id"],))
        return outbound_plan(settings=settings, scope_kind=TaskContext.restore(
            json.loads(batch["context_json"])).scope.kind.value, sequence=part["sequence"],
            first_text_sequence=first_text_sequence([row["text"] for row in rows]),
            text=part["text"], inputs=sealed_inputs(self.runtime, part["batch_id"]))

    def pending_review(self, part):
        """True while this group turn still waits for its image review verdict."""
        if not self._sealed(part)[2]:
            return False
        return self.plan_for(part) is None and self.messages.image_review.pending_for(part)

    def withheld_image(self, part):
        """The reviewed original a withhold decision keeps out of the group."""
        plan = self.plan_for(part)
        return plan if plan is not None and plan.decision == WITHHOLD else None

    def _sent_hash(self, part, receipt_hash):
        """Confirm a receipt names the payload this part was allowed to send.

        A reviewed part sends a recorded substitution instead of its sealed
        payload. The substitution is written before the send, so the receipt still
        proves that the reviewed decision -- not a later edit -- is what left.
        """
        if receipt_hash == part["payload_hash"]:
            return part["payload_hash"]
        review = getattr(self.messages, "image_review", None)
        if review is None:
            return part["payload_hash"]
        _batch, _context, _images, image_position, _sealed = self._sealed(part)
        return review.substituted_hash(part["part_id"], image_position=image_position)

    def enqueue_fallback(self, part, *, deadline_at):
        """Queue the separately authorized private delivery of a withheld image."""
        return self.messages.image_fallback.enqueue(part, deadline_at=deadline_at)

    def _forbidden_word_hit(self, part):
        batch = self.messages.batch(part["batch_id"])
        try:
            contributions = json.loads(batch["contributions_json"])
            settings = (contributions.get("reply_settings") or {}).get("settings") or {}
            policy = text_policy(settings)
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise TaskError("message_presentation_invalid", "original reply presentation settings are invalid") from error
        return policy.forbidden_word_guard(
            part["text"], scope_kind=TaskContext.restore(json.loads(batch["context_json"])).scope.kind.value)

    def _original(self, context, batch, at):
        self.messages.authorize(context, at)
        if batch["origin_key"] != context.key or batch["state"] != "ready":
            raise TaskError("message_batch_closed", "original reply is unavailable for delivery")
        generation = require(self.tasks.read(context, batch["generation_task_id"]))
        if generation.state != "succeeded":
            from .streaming_reply import stream_record, validate_stream
            if stream_record(self.messages, batch["batch_id"]) is None:
                raise TaskError("message_generation_pending", "only a completed original generation may be delivered")
            validate_stream(self.messages, batch, context, at)
        request = self.messages._request(batch, context, at)
        images, _reference, _image_part_id, image_position = self.messages.reply_images.read_binding(
            batch, context, at, request=request, with_position=True)
        parts = self.runtime.read_all("SELECT text FROM conversation_parts WHERE batch_id = ? ORDER BY sequence",
                                      (batch["batch_id"],))
        if reply_manifest(batch["batch_id"], batch["call_id"], tuple(part["text"] for part in parts), images,
                          image_position=image_position, action=batch["presentation_action"]) != batch["manifest_hash"]:
            raise TaskError("message_manifest_changed", "original reply action or parts changed after generation")
        if images and not self.sender.supports_images:
            raise TaskError("message_sender_media_unavailable", "original sender does not support image envelopes")
        if batch["presentation_action"] == "poke" and not self.sender.supports_poke:
            raise TaskError("message_sender_poke_unavailable", "original sender does not support native poke actions")

    @outcome
    def validate(self, spec, at):
        part = self._part(spec.request_ref)
        batch = self.messages.batch(part["batch_id"])
        self._original(spec.context, batch, at)
        if (spec.kind != DELIVERY_KIND or part["task_id"] != spec.task_id or
                part["sender_json"] != encode(self.sender.binding) or part["state"] == "cancelled"):
            raise TaskError("message_delivery_mismatch", "delivery must retain its original task and sender")
        if self.runtime.read_one("""SELECT 1 FROM conversation_parts WHERE batch_id = ?
            AND sequence < ? AND state != 'delivered'""", (part["batch_id"], part["sequence"])):
                raise TaskError("message_previous_unconfirmed", "a previous part has no delivery confirmation")
        if self._forbidden_word_hit(part) is not None:
            raise TaskError("forbidden_word_blocked", "reply contains a configured forbidden word")
        return True

    @outcome
    def queue_next(self, context, batch_id, *, deadline_at, not_before=None):
        with self.runtime.transaction() as connection:
            batch = self.messages.owned(context, batch_id)
            self._original(context, batch, self.tasks.now())
            part = connection.execute("""SELECT * FROM conversation_parts WHERE batch_id = ?
                AND state != 'delivered' ORDER BY sequence LIMIT 1""", (batch_id,)).fetchone()
            if part is None:
                return DeliveryQueueResult(None)
            if part["state"] == "failed":
                raise TaskError("message_delivery_failed", "the original part was confirmed not sent")
            if part["state"] != "pending":
                raise TaskError("message_delivery_unresolved", "original part requires reconciliation; no new send was queued")
            if part["task_id"]:
                task = require(self.tasks.read(context, part["task_id"]))
                if task.spec.deadline_at != deadline_at or (not_before is not None and task.spec.not_before != not_before):
                    raise TaskError("message_delivery_conflict", "queued delivery timing cannot be changed")
                return DeliveryQueueResult(task)
            definition = self.tasks.registrations[DELIVERY_KIND].definition
            if definition.binding != self.sender.binding:
                raise TaskError("message_sender_changed", "sender differs from the registered original task owner")
            task_id = "deliver-" + part["part_id"]
            connection.execute("UPDATE conversation_parts SET task_id = ?, sender_json = ? WHERE part_id = ?",
                               (task_id, encode(self.sender.binding), part["part_id"]))
            return DeliveryQueueResult(require(self.tasks.submit(TaskSpec(task_id, context, DELIVERY_KIND,
                part["part_id"], part["part_id"], not_before or self.tasks.now(), deadline_at))))

    def _dispatch(self, run):
        if run.supervisor is not self.tasks:
            raise ValueError("sender must use its original supervisor")
        with self.runtime.transaction() as connection:
            run.validate()
            part = self._part(run.task.spec.request_ref)
            if part["state"] != "pending" or part["operation_id"] is not None:
                raise TaskError("message_already_dispatched", "an original part must never be resubmitted")
            if self._forbidden_word_hit(part) is not None:
                raise TaskError("forbidden_word_blocked", "reply contains a configured forbidden word")
            images, image_position, content_hash = self._content(part)
            context = run.task.spec.context
            if context.scope.kind is ScopeKind.GROUP:
                try:
                    persist_hits(connection, evaluate_message(
                        owner_key=group_owner_key(context),
                        member_id=context.scope.account_id or context.scope.bot_id or "bot",
                        message_id=part["part_id"], message_text=part["text"],
                        occurred_at=self.tasks.now(), direction="outbound"), created_at=self.tasks.now())
                except Exception as error:
                    # Safety evidence is additive and never blocks delivery.
                    logger.warning("V2 outbound safety evidence persistence failed: %s", type(error).__name__)
            run.begin_effect()
            operation = OperationRef("send-" + part["part_id"], "conversation.delivery", run.task.spec.context.scope,
                                     VersionRef(part["part_id"], 1), part["part_id"])
            plan = self.outbound_plan(part)
            batch = self.messages.batch(part["batch_id"])
            poke = PokePlan() if batch["presentation_action"] == "poke" else None
            voice_required = batch["presentation_action"] == "voice_only"
            require(self.operations.reserve(operation, parameter_hash=digest([
                run.task.spec.context.key, content_hash, self.sender.binding]
                + ([plan.document()] if plan is not None else [])
                + ([{"poke": poke.document()}] if poke is not None else [])), observed_at=self.tasks.now()))
            run.record_operation(operation.operation_id)
            connection.execute("""UPDATE conversation_parts SET state = 'dispatched', operation_id = ?,
                dispatched_at = ? WHERE part_id = ?""", (operation.operation_id, stamp(self.tasks.now()), part["part_id"]))
            kind = ImageDeliveryEnvelope if images else DeliveryEnvelope
            return kind(part["part_id"], operation.operation_id, run.task.spec.context,
                part["sequence"], part["text"], content_hash, self.sender.binding, run.validate,
                plan=plan, poke=poke, voice_required=voice_required,
                **({"images": images, "image_position": image_position} if images else {}))

    def _unknown(self, part_id):
        with self.runtime.transaction() as connection:
            changed = connection.execute("UPDATE conversation_parts SET state = 'unknown' WHERE part_id = ? AND state = 'dispatched'", (part_id,))
            if changed.rowcount:
                self._operation_state(self._part(part_id), OperationState.UNKNOWN)

    def _operation_state(self, part, state):
        current = require(self.operations.get(part["operation_id"]))
        if current.state is not state:
            require(self.operations.transition(current.operation.operation_id, expected_state=current.state,
                                                next_state=state, observed_at=self.tasks.now()))

    async def deliver(self, run):
        envelope = self._dispatch(run)
        started = perf_counter()
        batch_id = self._part(envelope.part_id)["batch_id"]
        logger.info("[CompanionV2] 回复分段开始投递 batch=%s part=%s sequence=%d",
                    batch_id, envelope.part_id, envelope.sequence)
        try:
            receipt = await self.sender.send(envelope)
            if not isinstance(receipt, DeliveryReceipt):
                raise TypeError("sender returned no trusted receipt")
            if receipt.part_id != envelope.part_id or receipt.operation_id != envelope.operation_id:
                raise TaskError("message_receipt_mismatch", "sender returned another dispatch's receipt")
            # A callback may arrive after cancellation. Account for the original effect
            # without reviving its task, reading its sources, or scheduling another part.
            require(self.record_receipt(receipt))
            logger.info("[CompanionV2] 回复分段投递回执 batch=%s part=%s status=%s elapsed_ms=%d",
                        batch_id, envelope.part_id, receipt.status,
                        round((perf_counter() - started) * 1000))
        except asyncio.CancelledError:
            self._unknown(envelope.part_id)
            raise
        except Exception as error:
            self._unknown(envelope.part_id)
            logger.warning("[CompanionV2] 回复分段投递结果未知 batch=%s part=%s reason=%s elapsed_ms=%d",
                           batch_id, envelope.part_id,
                           error.code if isinstance(error, TaskError) else type(error).__name__,
                           round((perf_counter() - started) * 1000))
            return self._result(self._part(envelope.part_id))
        # The image was deliberately kept out of the group. Its separate private
        # delivery is queued only after the group receipt, so a reviewed image is
        # never sent anywhere the reviewer did not authorize.
        if self.messages.image_fallback is not None:
            try:
                self.enqueue_fallback(self._part(envelope.part_id), deadline_at=run.task.spec.deadline_at)
            except TaskError:
                pass  # A missing private route keeps the original blocked; it never reopens the group.
        return self._result(self._part(envelope.part_id))

    @outcome
    def record_receipt(self, receipt: DeliveryReceipt):
        """Trusted adapter callback, not a user/model tool or a grant to send."""
        with self.runtime.transaction() as connection:
            part = self._part(receipt.part_id)
            batch = self.messages.batch(part["batch_id"])
            if (part["operation_id"] != receipt.operation_id or batch["origin_key"] != receipt.origin_key or
                    receipt.payload_hash != self._sent_hash(part, receipt.payload_hash) or
                    part["sender_json"] != encode(receipt.sender) or
                    part["dispatched_at"] is None):
                raise TaskError("message_receipt_mismatch", "receipt does not belong to this original dispatch")
            if receipt.delivered_at is not None and not (
                    datetime.fromisoformat(part["dispatched_at"]) <= receipt.delivered_at <= self.tasks.now()):
                raise TaskError("message_receipt_time", "delivery time must be within the original dispatch interval")
            prior = connection.execute("SELECT receipt_json FROM conversation_delivery_receipts WHERE part_id = ? AND receipt_ref = ?",
                                       (receipt.part_id, receipt.receipt_ref)).fetchone()
            if prior is not None:
                if prior["receipt_json"] != encode(receipt):
                    raise TaskError("message_receipt_conflict", "receipt identity cannot change its original outcome")
                return part["state"]
            state = "failed" if receipt.status == "not_sent" else receipt.status
            if (part["state"] == "failed" and state not in ("failed", "unknown") or
                    part["state"] == "delivered" and state == "failed" or
                    part["platform_ref"] is not None and receipt.platform_ref not in (None, part["platform_ref"]) or
                    part["state"] == "delivered" and state == "delivered" and stamp(receipt.delivered_at) != part["delivered_at"]):
                raise TaskError("message_receipt_conflict", "confirmed original delivery outcome is immutable")
            connection.execute("INSERT INTO conversation_delivery_receipts VALUES (?, ?, ?, ?)",
                               (receipt.part_id, receipt.receipt_ref, encode(receipt), stamp(self.tasks.now())))
            if part["state"] in ("delivered", "failed") or (part["state"] == "accepted" and state == "unknown"):
                return part["state"]
            connection.execute("""UPDATE conversation_parts SET state = ?, receipt_ref = ?,
                platform_ref = COALESCE(?, platform_ref), delivered_at = ? WHERE part_id = ?""",
                (state, receipt.receipt_ref, receipt.platform_ref,
                 stamp(receipt.delivered_at) if receipt.delivered_at else None, receipt.part_id))
            self._operation_state(part, OperationState.COMPLETED if state in ("delivered", "failed") else
                                  OperationState.UNKNOWN if state == "unknown" else OperationState.ACCEPTED)
            if state == "delivered":
                connection.execute("""INSERT INTO conversation_sent_history
                    (part_id, batch_id, origin_key, delivered_at, receipt_ref) VALUES (?, ?, ?, ?, ?)""",
                    (receipt.part_id, part["batch_id"], batch["origin_key"], stamp(receipt.delivered_at), receipt.receipt_ref))
                first_confirmed_part = connection.execute("""SELECT COUNT(*) AS count
                    FROM conversation_sent_history WHERE batch_id = ?""", (part["batch_id"],)).fetchone()["count"] == 1
                if first_confirmed_part and self.messages.expression_style_context is not None:
                    connection.execute("SAVEPOINT expression_feedback_delivery")
                    try:
                        context = TaskContext.restore(json.loads(batch["context_json"]))
                        self.messages.expression_style_context.confirm_delivery(connection,
                            batch_id=part["batch_id"], context=context, delivered_at=receipt.delivered_at)
                        connection.execute("RELEASE SAVEPOINT expression_feedback_delivery")
                    except Exception as error:
                        connection.execute("ROLLBACK TO SAVEPOINT expression_feedback_delivery")
                        connection.execute("RELEASE SAVEPOINT expression_feedback_delivery")
                        logger.warning("V2 expression feedback delivery accounting failed: %s", type(error).__name__)
            return state

    @outcome
    def recover_dispatches(self, *, limit=32):
        require(self.tasks.recover(limit=limit))
        with self.runtime.transaction() as connection:
            rows = connection.execute("""SELECT p.part_id FROM conversation_parts p
                JOIN execution_tasks t ON t.task_id = p.task_id WHERE p.state = 'dispatched'
                AND t.state = 'uncertain' ORDER BY p.part_id LIMIT ?""", (limit,)).fetchall()
            for row in rows:
                connection.execute("UPDATE conversation_parts SET state = 'unknown' WHERE part_id = ?", (row["part_id"],))
                self._operation_state(self._part(row["part_id"]), OperationState.UNKNOWN)
            return tuple(row["part_id"] for row in rows)

    @staticmethod
    def _result(part):
        if part["state"] == "delivered":
            return TaskResult("succeeded", "committed", result_ref=part["part_id"],
                              receipt_ref=part["receipt_ref"], operation_id=part["operation_id"])
        if part["state"] == "failed":
            return TaskResult("failed", "not_committed", receipt_ref=part["receipt_ref"], operation_id=part["operation_id"])
        return TaskResult("uncertain", "unknown", operation_id=part["operation_id"])

    @outcome
    def reconcile_task(self, context, part_id):
        """Install a known receipt in a stopped uncertain task, without another send."""
        with self.runtime.transaction():
            part = self._part(part_id)
            self.messages.owned(context, part["batch_id"])
            result = self._result(part)
            if result.status == "uncertain":
                raise TaskError("message_delivery_unresolved", "there is no confirmed result to reconcile")
            task = require(self.tasks.read(context, part["task_id"]))
            if task.state == result.status:
                return task
            return require(self.tasks.reconcile(context, task.task_id, expected_revision=task.revision, result=result))
