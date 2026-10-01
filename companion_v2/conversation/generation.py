"""Asynchronous original-role reply generation for the local conversation profile."""

from dataclasses import replace
import json

from companion_v2.execution.models import TaskError, TaskResult, digest
from companion_v2.model_gateway.service import LocalModelGateway

from .foreground import GroundedDraftReviewer
from .messages import ConversationMessages
from .media.reply import reply_manifest
from .segmentation import SegmentationPolicy
from .reply_settings import (group_safety_settings, validate as validate_settings,
                              voice_policy as captured_voice_policy)
from .reply_preparation import observed_statements, prepare_reply
from .text_processing import text_policy
from .voice_reply import VoiceReplyPolicy, capability_instruction as voice_capability_instruction, eligible
from companion_v2.delivery.media import payload_hash
from companion_v2.foundation.refs import ScopeKind


def single_part(text):
    return (text,)


class LocalReplyGenerator:
    def __init__(self, messages: ConversationMessages, gateway: LocalModelGateway, *, split=single_part,
                 segmentation=SegmentationPolicy(), voice_policy=None):
        if messages.tasks is not gateway.tasks or not callable(split):
            raise ValueError("reply generation requires the original gateway and a trusted segmentation policy")
        self.messages = messages
        self.gateway = gateway
        self.split = split
        if not isinstance(segmentation, SegmentationPolicy):
            raise ValueError("reply segmentation needs a validated policy")
        self.segmentation = segmentation
        if voice_policy is not None and not isinstance(voice_policy, VoiceReplyPolicy):
            raise ValueError("reply voice needs a validated policy")
        self.voice_policy = voice_policy
        self.reviewer = GroundedDraftReviewer()

    def _request(self, run, segmentation=None, streaming=None, voice=None, presentation=None):
        request = self.messages.request(run)
        request = replace(request, streaming=streaming)
        instruction = (segmentation or self.segmentation).instruction
        if presentation is not None and presentation.instruction:
            instruction = (instruction + "\n" + presentation.instruction).strip()
        if voice is not None:
            instruction = (instruction + "\n" + voice_capability_instruction(voice)
                           + ("\n" + voice.instruction if voice.instruction else "")).strip()
        return replace(request, instruction=instruction + "\n" + request.instruction) if instruction else request

    async def generate(self, run):
        if run.supervisor is not self.messages.tasks:
            raise ValueError("reply generation must use the original supervisor")
        captured = json.loads(self.messages.batch(run.task.spec.request_ref)["contributions_json"]).get("reply_settings")
        segmentation = validate_settings(captured["settings"]) if captured is not None else self.segmentation
        presentation = text_policy(captured["settings"] if captured is not None else {})
        streaming = (captured["settings"]["streaming"]
                     if captured is not None and captured.get("streaming_explicit", True) else None)
        image_position = captured["settings"].get("image_position", "after_text") if captured is not None else "after_text"
        voice = (captured_voice_policy(captured["settings"])
                 if captured is not None and "voice_enabled" in captured["settings"] else self.voice_policy)
        semantic = getattr(self.messages, "semantics", None)
        if semantic is not None:
            await semantic.prepare_turn(run)
        request = self._request(run, segmentation, streaming, voice, presentation)
        caption_material = None
        caption_service = getattr(self.messages, "context_image_caption", None)
        if caption_service is not None and captured is not None:
            caption = await caption_service.summarize(run, run.task.spec.request_ref, captured["settings"])
            if caption:
                from .foreground import PromptMaterial
                caption_material = PromptMaterial("conversation.context_image_caption", "historical_image_caption",
                    "以下是对仍获授权的群历史原图所作的临时摘要，仅用于理解上下文；它不是来源证据，也不是持久事实：" + caption)
                request = replace(request, context=replace(request.context, materials=request.context.materials + (caption_material,)),
                    instruction=request.instruction + "\n历史图片摘要只作临时辅助；不要把摘要当作当前画面、原图证据或持久记忆。")
        tools = self.messages.tools
        participation = getattr(tools, "group_participation", None)
        session = self.gateway.open_session(run, request, tools=tools.catalog_for(
            run.task.spec.context, run.task.spec.request_ref) if tools else ())
        history = ()
        completion = None
        try:
            while True:
                current = self._request(run, segmentation, streaming, voice, presentation)
                if caption_material is not None:
                    current = replace(current, context=replace(current.context, materials=current.context.materials + (caption_material,)),
                        instruction=current.instruction + "\n历史图片摘要只作临时辅助；不要把摘要当作当前画面、原图证据或持久记忆。")
                if session.round_no == 8:
                    current = replace(current, instruction=current.instruction +
                        "\n本轮工具已结束。按已有实际结果自然回复，说明未完成部分；不要声称未执行的操作已成功。")
                if tools is not None:
                    history = tools.refresh_history(self.messages.batch(run.task.spec.request_ref), run.task.spec.context,
                                                    current, history, self.messages.tasks.now())
                completion = await session.generate(current, history=history,
                    owner_refresh=(lambda original, request, previous, fresh: tools.validate_owner_refresh(
                        run.task.spec.context, run.task.spec.request_ref, original, request, previous, fresh)) if tools else None,
                    media_refresh=lambda original, request: self.messages.generated_images.validate_refresh(
                        run.task.spec.request_ref, run.task.spec.context, self.messages.tasks.now(), original, request))
                # Validate the exact materials used for this round again before
                # another owner command or a sendable manifest can be created.
                self.messages.request(run)
                if completion.draft is not None:
                    if participation is not None:
                        participation.allow_reply(run.task.spec.context, run.task.spec.request_ref)
                    break
                if tools is None:
                    raise TaskError("model_tools_unavailable", "this reply has no registered tool owners")
                for call in completion.tool_calls:
                    run.validate()
                    history += (await tools.execute_async(run, completion.call_id, call),)
                    if participation is not None and participation.finish_if_skipped(
                            run.task.spec.context, run.task.spec.request_ref):
                        return TaskResult("succeeded", result_ref=run.task.spec.request_ref)
            draft_text = completion.draft.text
            safety = group_safety_settings(captured["settings"] if captured is not None else {})
            if (run.task.spec.context.scope.kind is ScopeKind.GROUP
                    and safety["enable_group_reality_promise_guard"]):
                draft_text, _ = presentation.reality_promise_guard(
                    draft_text, statements=observed_statements(completion.draft))
            if presentation.forbidden_word_guard(
                    draft_text, scope_kind=run.task.spec.context.scope.kind.value) is not None:
                raise TaskError("forbidden_word_blocked", "reply contains a configured forbidden word")
            try:
                prepared = prepare_reply(draft_text, segmentation, presentation, voice,
                    statements=observed_statements(completion.draft), split=self.split)
            except ValueError as error:
                raise TaskError("message_parts_invalid", "reply contains no bounded visible text") from error
            parts = prepared.parts
            if (not isinstance(parts, tuple) or not 1 <= len(parts) <= 64 or
                    any(not isinstance(part, str) or not part.strip() for part in parts) or
                    sum(map(len, parts)) > 65536):
                raise TaskError("message_parts_invalid", "reply presentation must produce bounded visible parts")
            speech = ("",) * len(parts)
            candidate_reasons = ("voice_disabled",) * len(parts)
            if voice is not None:
                input_text = "\n".join(material.payload for material in request.context.materials
                    if material.purpose == "current_source" or material.purpose.startswith("merged_input:"))
                if eligible(voice, input_text=input_text, kind=run.task.spec.context.scope.kind.value,
                            batch_id=run.task.spec.request_ref):
                    decisions = prepared.speech(voice)
                    speech = tuple(item[0] for item in decisions)
                    candidate_reasons = tuple(item[1] for item in decisions)
                else:
                    candidate_reasons = ("trigger_skipped",) * len(parts)
            with self.messages.runtime.transaction() as connection:
                current = self.messages.request(run)
                if not self.reviewer.review(completion.draft, current.context,
                                            observed_at=self.messages.tasks.now()).approved:
                    raise TaskError("draft_not_grounded", "declared evidence was not in the original sealed materials")
                batch_id = run.task.spec.request_ref
                row = self.messages.batch(batch_id)
                if row["state"] != "sealed" or row["call_id"] is not None:
                    raise TaskError("message_manifest_exists", "original reply cannot be generated twice")
                images = self.messages.reply_images.select(completion.draft, current)
                image_sequence = len(parts)
                if semantic is not None and images and len(parts) < 64:
                    mode = semantic.reactions.delivery_mode(run.task.spec.context, batch_id, images)
                    if mode == "separate_before":
                        parts = ("",) + parts
                        speech = ("",) + speech
                        candidate_reasons = ("empty_part",) + candidate_reasons
                        image_sequence = 1
                    elif mode == "separate_after":
                        parts = parts + ("",)
                        speech = speech + ("",)
                        candidate_reasons = candidate_reasons + ("empty_part",)
                        image_sequence = len(parts)
                manifest = reply_manifest(batch_id, completion.call_id, parts, images, image_position=image_position)
                for sequence, text in enumerate(parts, 1):
                    part_id = "part-" + digest([batch_id, sequence])
                    connection.execute("""INSERT INTO conversation_parts
                        (part_id, batch_id, sequence, text, payload_hash, state)
                        VALUES (?, ?, ?, ?, ?, 'pending')""", (part_id, batch_id, sequence, text,
                            payload_hash(text, images if sequence == image_sequence else (), image_position=image_position)))
                    reason = candidate_reasons[sequence - 1]
                    connection.execute("""INSERT INTO conversation_voice_diagnostics
                        (part_id, candidate_reason, render_state, component_order_json, text_hidden)
                        VALUES (?, ?, ?, '[]', 0)""", (part_id, reason,
                            "pending" if reason == "planned" else "not_applicable"))
                    if speech and speech[sequence - 1]:
                        policy = voice
                        connection.execute("""INSERT INTO conversation_voice_parts
                            (part_id, speech, provider_id, delivery_mode, position, timeout_seconds, cooldown_seconds)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""", (part_id, speech[sequence - 1],
                            policy.provider_for_language(), policy.delivery_mode, policy.position,
                            policy.timeout_seconds, policy.cooldown_seconds))
                image_part_id = "part-" + digest([batch_id, image_sequence])
                self.messages.reply_images.publish(row, run.task.spec.context, image_part_id, images,
                                                   self.messages.tasks.now(), image_position=image_position)
                # A group image is reviewed before it may reach the collective
                # audience. The verdict is registered in the same transaction as
                # the sealed manifest it belongs to.
                self.messages.image_review.register(run.task.spec.context, batch_id, image_part_id, images,
                                                    image_position=image_position)
                connection.execute("""UPDATE conversation_batches SET state = 'ready', revision = revision + 1,
                    call_id = ?, manifest_hash = ?, part_count = ? WHERE batch_id = ?""",
                    (completion.call_id, manifest, len(parts), batch_id))
            return TaskResult("succeeded", result_ref=batch_id)
        except BaseException:
            if completion is not None:
                self.gateway.ledger.discard(completion.call_id)
            raise
