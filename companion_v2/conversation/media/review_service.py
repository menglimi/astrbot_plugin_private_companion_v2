"""Run one group image review as a registered background model task.

The verdict is produced by the configured vision provider and stored in the review
ledger. A review that could not be completed is stored as an explicit
``unavailable`` verdict rather than being retried indefinitely: an unknown answer
is never treated as an approval, and the delivery decision only ever moves an
image away from the group audience.
"""

from __future__ import annotations

import base64
from datetime import timedelta
import json

from companion_v2.conversation.foreground import (BackgroundPromptTrigger, PromptMaterial,
                                                  PromptRequest, SealedForegroundContext)
from companion_v2.execution.models import (Lane, ProviderBinding, SideEffect, TaskContext, TaskDefinition,
                                           TaskError, TaskRegistration, TaskResult, TaskSpec, digest, encode,
                                           require, stamp)
from companion_v2.execution.runner import ExactTaskRunner
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import ScopeKind
from companion_v2.model_gateway.models import ModelTaskProfile

from .models import CapturedImage, ImageDescriptor, PromptImage
from .review import GroupImageReview, check_verdict, decide, merge_answers, parse_answer, review_prompt, verdict_document


KIND = "conversation.image_review"
OWNER = "conversation.image_review"
ACTION = "image.review"
PROFILE_KIND = "image_review"
TIMEOUT_SECONDS = 30
MAX_OUTPUT_TOKENS = 80
CONCURRENCY = 1


def image_review_profile(provider, *, max_output_tokens=MAX_OUTPUT_TOKENS, timeout_seconds=20):
    """The background vision profile this review needs; disabled until configured."""
    return ModelTaskProfile(PROFILE_KIND, Lane.BACKGROUND, provider,
        "对群聊成图做可见内容安全分类，只返回固定 JSON 标签与置信度。",
        max_output_tokens=max_output_tokens, capabilities=("text", "image"),
        timeout_seconds=timeout_seconds)


class GroupImageReviewService:
    """Host-driven review planner and executor, sharing the original supervisor."""

    def __init__(self, runtime, *, notify=None):
        """Register the task kind before the conversation owner exists."""
        self.review = None
        self.messages = None
        self.runtime = runtime
        self.notify = notify or (lambda: None)
        self.pending: dict[str, dict] = {}
        self.results: dict[str, dict] = {}
        self.closed = False
        self.app = None
        self.runner = None
        self.registrations = (TaskRegistration(TaskDefinition(KIND, OWNER, ACTION, Lane.BACKGROUND,
            side_effect=SideEffect.LOCAL,
            binding=ProviderBinding(OWNER, "local", "1", "image-review-1"),
            timeout_seconds=TIMEOUT_SECONDS, max_attempts=1, concurrency=CONCURRENCY), self.validate),)

    def attach(self, app):
        self.app, self.tasks, self.gateway = app, app.tasks, app.gateway
        self.runner = ExactTaskRunner(self.tasks, frozenset({KIND}), self.generate)

    def attach_review(self, review):
        """Bind the conversation owner's review instance to this executor."""
        if review.runtime is not self.runtime or review.messages is None:
            raise ValueError("image review must use its original runtime and conversation owner")
        self.review = review
        self.messages = review.messages

    # -- planner -------------------------------------------------------

    @outcome
    def advance(self):
        """Submit due pending reviews; bounded and never blocking the caller."""
        if self.closed or self.app is None or self.review is None:
            return False
        for task_id, (_, worker) in tuple(self.pending.items()):
            if worker.done():
                if not worker.cancelled():
                    worker.exception()
                del self.pending[task_id]
        capacity = max(0, CONCURRENCY - len(self.pending))
        if not capacity:
            return False
        rows = self.review.pending_requests(limit=capacity)
        submitted = 0
        for row in rows:
            try:
                self.submit(row["review_key"])
            except TaskError as error:
                self.results[row["review_key"]] = {"state": "blocked", "code": error.code}
                continue
            submitted += 1
        return submitted == capacity

    def submit(self, review_key):
        row = self.review.row(review_key)
        if row is None or row["state"] != "pending":
            raise TaskError("image_review_unavailable", "the original review request is unavailable")
        batch = self.runtime.read_one("SELECT * FROM conversation_batches WHERE batch_id = ?", (row["batch_id"],))
        if batch is None:
            raise TaskError("image_review_unavailable", "the original review batch is unavailable")
        context = TaskContext.restore(json.loads(batch["context_json"]))
        if context.key != row["origin_key"] or context.scope.kind is not ScopeKind.GROUP:
            raise TaskError("image_review_context", "review must retain its original group context")
        with self.runtime.transaction():
            require(self.tasks.submit(TaskSpec(review_key, context, KIND, review_key, review_key,
                self.tasks.now(), self.tasks.now() + timedelta(seconds=TIMEOUT_SECONDS))))
        return review_key

    # -- execution -----------------------------------------------------

    @outcome
    def validate(self, spec, at):
        job = self.pending.get(spec.task_id)
        row = self.review.row(spec.task_id)
        if job is None or row is None or row["state"] != "pending" or row["origin_key"] != spec.context.key:
            raise TaskError("image_review_unavailable", "the original review request is unavailable")
        return True

    def _content(self, item, descriptor):
        """Read one reviewed original from its governed blob, never from a URL."""
        source = item["source"]
        row = self.runtime.read_one("""SELECT * FROM conversation_image_payloads
            WHERE source_id = ? AND source_lineage = ? AND source_revision = ?""",
            (source["source_id"], source["version"]["lineage_id"], source["version"]["revision"]))
        if row is None or row["descriptor_json"] != encode(descriptor):
            raise TaskError("image_review_original", "the reviewed provider original is unavailable")
        return row["content"]

    def images(self, target):
        from companion_v2.conversation.messages import source_from_document
        result = []
        with self.runtime.read_snapshot():
            for item in target["images"]:
                descriptor = ImageDescriptor(**item["descriptor"])
                content = self._content(item, descriptor)
                captured = CapturedImage(descriptor, content)
                result.append(PromptImage(source_from_document(item["source"]),
                                          source_from_document(item["parent"]), descriptor,
                                          base64.b64encode(captured.content).decode("ascii")))
        return tuple(result)

    async def _one(self, run, job, provider_id, prompt):
        context, target, at = job["context"], job["target"], self.tasks.now()
        request = PromptRequest(
            BackgroundPromptTrigger(digest([run.task.task_id, provider_id]), context.actor.principal,
                                    context.scope, at),
            "群聊成图安全审核",
            SealedForegroundContext((PromptMaterial(OWNER, "group_image_review_target",
                encode({"part_id": target["part_id"], "image_count": len(target["images"])})),), (), ()),
            prompt, context.role_binding, output_format="image_review",
            images=self.images(target))
        completion = await self.gateway.generate(run, request)
        if completion.draft is None:
            return None
        label, confidence = parse_answer(completion.draft.text)
        return {"provider_id": provider_id, "label": label, "confidence": confidence}

    async def generate(self, run):
        job = self.pending[run.task.task_id]
        context = job["context"]
        row = self.review.row(run.task.task_id)
        if row is None or row["state"] != "pending":
            raise TaskError("image_review_unavailable", "the original review request is unavailable")
        stored = json.loads(row["review_json"])
        job["target"] = stored["target"]
        settings = self.review.settings_for(context)
        mode = settings["group_nsfw_image_review_mode"]
        threshold = settings["group_nsfw_image_review_min_confidence"]
        prompt = review_prompt(settings)
        revision = (stored.get("revision") or 0) + 1
        run.validate()
        answers, providers, reason = [], [], None
        try:
            wanted = [self.review.providers(context)[0]] if mode == "single" else list(self.review.providers(context))
            for provider_id in wanted:
                if not provider_id:
                    reason = "没有配置审核用的视觉模型"
                    continue
                answer = await self._one(run, job, provider_id, prompt)
                if answer is None:
                    reason = "审核模型没有返回结果"
                    continue
                if answer["label"] == "uncertain":
                    reason = "审核模型未能确认画面"
                    continue
                if answer["confidence"] < threshold:
                    reason = f"审核置信度 {answer['confidence']:.2f} 低于阈值 {threshold:.2f}"
                    continue
                answers.append(answer)
                providers.append(provider_id)
                if mode == "single" or answer["label"] in ("adult_nsfw", "disallowed"):
                    break
        except TaskError as error:
            reason = str(error) or error.code
        return self._record(run, row, settings, mode, revision, answers, providers, reason)

    def _document(self, settings, mode, revision, answers, providers, reason):
        sensitivity = settings["group_nsfw_image_review_sensitivity"]
        if len(answers) == 2:
            merged = merge_answers(answers)
            if merged is not None:
                return verdict_document("reviewed", mode, sensitivity, label=merged["label"],
                    confidence=merged["confidence"], provider_ids=merged["provider_ids"],
                    answers=merged["answers"], revision=revision)
        if answers:
            answer = answers[0]
            return verdict_document("reviewed", mode, sensitivity, label=answer["label"],
                confidence=answer["confidence"], provider_ids=[answer["provider_id"]],
                answers=answers, revision=revision)
        return verdict_document("unavailable", mode, sensitivity, provider_ids=providers,
                                reason=reason or "审核没有取得可用结论", revision=revision)

    def _record(self, run, row, settings, mode, revision, answers, providers, reason):
        saved = json.loads(row["review_json"])
        document = self._document(settings, mode, revision, answers, providers, reason)
        document.update({name: saved[name] for name in ("origin_key", "role_key", "group_key", "created_at")})
        document["target"] = saved["target"]
        document["updated_at"] = stamp(self.tasks.now())
        check_verdict(document)
        decision = decide(document["label"], settings, ran=document["state"] == "reviewed")[0]
        with self.runtime.transaction():
            run.validate()
            run.begin_effect()
            current = self.review.row(row["review_key"])
            if current is None or current["state"] != "pending":
                raise TaskError("image_review_conflict", "a decided review cannot be decided again")
            self.review.store(row["review_key"], document)
        self.results[row["review_key"]] = {"state": document["state"], "label": document["label"],
                                           "decision": decision}
        self.notify()
        return TaskResult("succeeded", effect="committed", result_ref=row["review_key"])

    # -- lifecycle -----------------------------------------------------

    @property
    def active_handles(self):
        handles = self.runner.active_handles if self.runner is not None else ()
        return handles + tuple("image-review:" + key for key in self.pending)

    def cancel_running(self):
        for _, worker in self.pending.values():
            worker.cancel()

    async def close(self):
        self.closed = True
        self.cancel_running()
        if self.runner is not None:
            await self.runner.close()


def timedelta_seconds(seconds):
    from datetime import timedelta
    return timedelta(seconds=seconds)


__all__ = ["ACTION", "CONCURRENCY", "KIND", "OWNER", "PROFILE_KIND", "TIMEOUT_SECONDS",
           "GroupImageReviewService", "image_review_profile"]
