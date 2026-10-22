"""Bounded reminiscence contact candidates from adopted relationship memories.

When a role and participant have adopted ``emotion_episode`` or relationship
``context`` memories from earlier conversations (at least several hours old so
it is a genuine flashback rather than a repeat of the current turn), the role
can occasionally recall that shared moment in an ``affection`` or ``care``
contact. Each (memory_id, revision) is considered at most once per window via
the durable contact task ledger.
"""

from collections import OrderedDict
from datetime import datetime, timedelta
import json

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import RoleOwnerRef, ScopeKind, SourceRef, SubjectKind, VersionRef
from companion_v2.relationships.models import EmotionSubject, RelationshipMemoryKind, RelationshipMemoryState
from companion_v2.relationships.provenance import same_private_route
from companion_v2.sources.dependencies import link
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord

from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


PAGE_SIZE = 16
POLL_INTERVAL = timedelta(seconds=60)
MIN_REMINISCENCE_AGE = timedelta(hours=12)
REMINISCENCE_WINDOW = timedelta(hours=2)
SOURCE_OWNER = "proactive.reminiscence"


class ReminiscenceContactEvents:
    """Revision-bound flashbacks of adopted relationship memories."""

    def __init__(self, contacts, relationships):
        if contacts.runtime is not relationships.runtime:
            raise ValueError("reminiscence contacts must share the original relationship runtime")
        self.contacts, self.relationships, self.runtime = contacts, relationships, relationships.runtime
        self.tasks = contacts.tasks
        self._scans = OrderedDict()
        self.guard = bind(self.runtime, SOURCE_OWNER, self._validate_source)

    def close(self):
        self.guard.close()
        self._scans.clear()

    @staticmethod
    def _owner(context):
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id)

    def _memory(self, context, memory_id, at):
        if (context.scope.kind is not ScopeKind.PRIVATE
                or context.audience.recipients != (context.actor.subject,)
                or context.actor.subject.kind is not SubjectKind.HUMAN):
            raise TaskError("contact_reminiscence_scope", "reminiscence requires the exact private participant")
        result = self.relationships.read(memory_id, actor=context.actor, scope=context.scope, observed_at=at)
        if not result.is_success:
            raise TaskError("contact_reminiscence_unavailable", result.failure.reason)
        memory = result.unwrap()
        if (memory.owner != self._owner(context)
                or memory.subject != context.actor.subject
                or memory.state is not RelationshipMemoryState.ADOPTED
                or memory.adopted_by is None
                or not same_private_route(memory.scope, context.scope)
                or any(not same_private_route(source.scope, context.scope) for source in memory.sources)
                or memory.updated_at > at
                or at - memory.observed_at < MIN_REMINISCENCE_AGE):
            raise TaskError("contact_reminiscence_changed", "adopted relationship memory is not eligible for reminiscence")
        return memory

    @staticmethod
    def _purpose(memory):
        if (memory.kind is RelationshipMemoryKind.EMOTION_EPISODE
                and memory.emotion_subject is EmotionSubject.HUMAN):
            return "care"
        return "affection"

    @staticmethod
    def _material(memory):
        return {
            "event": "shared_memory_reminiscence",
            "memory_id": memory.memory_id,
            "revision": memory.revision,
            "kind": memory.kind.value,
            "emotion_subject": memory.emotion_subject.value if memory.emotion_subject else None,
            "observed_at": stamp(memory.observed_at),
            "updated_at": stamp(memory.updated_at),
            "interpretation": memory.interpretation[:2048],
            "meaning": ("这是角色与当前用户在过往相处中留下的、经确认采纳的关系理解或情绪片段；"
                        "只作为此刻偶然回想起来的共同记忆由头，带着熟稔余温顺口提起或轻轻挂念，"
                        "不把过去那次情绪当成对方此刻正在经历的现状，也不生硬背诵记录原文。"),
        }

    @staticmethod
    def _source_ref(context, memory):
        identifier = "contact-reminiscence-source-" + digest(
            [context.key, memory.memory_id, memory.revision])
        return SourceRef(identifier, SOURCE_OWNER, context.scope, VersionRef(identifier, 1), memory.updated_at)

    def _project(self, context, memory, at):
        body = self._material(memory)
        reference = self._source_ref(context, memory)
        receipt = {
            "context": json.loads(encode(context)),
            "memory_id": memory.memory_id,
            "revision": memory.revision,
            "memory_hash": digest(memory),
        }
        payload = json.dumps({**body, "_receipt": receipt}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.runtime.transaction():
            require(self.contacts.sources.publish(
                SourceRecord(reference, context.audience, digest(payload), payload), observed_at=at))
            link(self.runtime, reference, memory.sources, at)
        require(self.contacts.sources.validate_reference_for_audience(
            reference, recipient=context.actor.subject, observed_at=at))
        return reference

    def _validate_source(self, source, at):
        try:
            payload = json.loads(source.payload)
            receipt = payload.pop("_receipt")
            if type(payload) is not dict or type(receipt) is not dict or set(receipt) != {
                    "context", "memory_id", "revision", "memory_hash"}:
                raise ValueError("invalid reminiscence source receipt")
            context = TaskContext.restore(receipt["context"])
            memory = self._memory(context, receipt["memory_id"], at)
            expected_ref = self._source_ref(context, memory)
            if (memory.revision != receipt["revision"] or digest(memory) != receipt["memory_hash"]
                    or source.reference != expected_ref or source.audience != context.audience
                    or payload != self._material(memory) or source.content_hash != digest(source.payload)):
                raise ValueError("original reminiscence memory changed")
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_reminiscence_source_changed",
                            "original relationship memory cannot attest this source") from error

    @staticmethod
    def _event_key(context, memory):
        return digest([context.key, memory.memory_id, memory.revision])

    def _known(self, context, opportunity):
        identifier = self.contacts.task_id(context, opportunity)
        return self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (identifier,)) or self.runtime.read_one(
            "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (identifier,))

    def select(self, context, preferences, at, *, purpose=None):
        """Scan adopted relationship memories for one mature, unshared flashback."""
        token = preferences.snapshot.resolution_token
        state = self._scans.get(context.key)
        if state is None or state[0] != token:
            state = (token, None, at)
        self._scans[context.key] = state
        self._scans.move_to_end(context.key)
        while len(self._scans) > 1024:
            self._scans.popitem(last=False)
        _, cursor, ready_at = state
        if ready_at > at:
            return None, False
        if all(preferences.reason(candidate) for candidate in ("affection", "care")):
            self._scans[context.key] = (token, None, at + POLL_INTERVAL)
            return None, False
        result = self.relationships.adopted_for_relationship(
            actor=context.actor, scope=context.scope, limit=PAGE_SIZE, after_id=cursor, observed_at=at)
        if not result.is_success:
            self._scans[context.key] = (token, None, at + POLL_INTERVAL)
            return None, False
        records = result.unwrap()
        for memory in records:
            cursor = memory.memory_id
            self._scans[context.key] = (token, cursor, at)
            if at - memory.observed_at < MIN_REMINISCENCE_AGE:
                continue
            candidate_purpose = self._purpose(memory)
            if purpose is not None and purpose != candidate_purpose:
                continue
            if preferences.reason(candidate_purpose):
                continue
            try:
                verified = self._memory(context, memory.memory_id, at)
            except TaskError:
                continue
            opened = max(verified.updated_at, verified.observed_at + MIN_REMINISCENCE_AGE)
            if at < opened:
                continue
            # Unlike ephemeral activity events, a reminiscence flashback opens a
            # bounded window when selected and retires permanently under its deterministic ID.
            opportunity = Opportunity("reminiscence-" + self._event_key(context, verified),
                context.scope, at, at + REMINISCENCE_WINDOW)
            if self._known(context, opportunity):
                continue
            try:
                source = self._project(context, verified, at)
            except (TaskError, KeyError, TypeError, ValueError):
                continue
            marker = {
                "memory_id": verified.memory_id,
                "revision": verified.revision,
                "memory_hash": digest(verified),
                "purpose": candidate_purpose,
                "opened_at": stamp(opportunity.opened_at),
                "expires_at": stamp(opportunity.expires_at),
            }
            if candidate_purpose == "care":
                summary = ("角色忽然回想起对方以前聊起过的一段心情或在意的事，想带着心底的默契轻轻问候一句近况；"
                           "记得那是过去的事，不把当时的情绪当成现在的事实，不合适就跳过。")
            else:
                summary = ("角色偶然回想起两人之前相处中留下的一段默契或共同记忆，心里泛起一点温和余韵，想顺口跟对方提一句；"
                           "语气自然熟稔，不背诵档案，不合适就跳过。")
            thought = Thought("reminiscence-event-" + digest(marker), opportunity, ThoughtKind.CONVERSATION, summary,
                              EvidenceSnapshot(context.scope, at, (source,)), 1.0)
            return (opportunity, (ContactIntent(candidate_purpose, thought),), marker), True
        more = len(records) == PAGE_SIZE
        self._scans[context.key] = (token, cursor if more else None, at if more else at + POLL_INTERVAL)
        return None, more

    def validate(self, context, marker, at):
        if not isinstance(marker, dict) or set(marker) != {
                "memory_id", "revision", "memory_hash", "purpose", "opened_at", "expires_at"}:
            raise TaskError("contact_reminiscence_invalid", "reminiscence contact requires its exact original marker")
        memory = self._memory(context, marker["memory_id"], at)
        if memory.revision != marker["revision"] or digest(memory) != marker["memory_hash"]:
            raise TaskError("contact_reminiscence_changed", "relationship memory changed after reminiscence selection")
        purpose = self._purpose(memory)
        if marker["purpose"] != purpose:
            raise TaskError("contact_reminiscence_changed", "reminiscence cannot change its purpose")
        try:
            opened = datetime.fromisoformat(marker["opened_at"])
            expires = datetime.fromisoformat(marker["expires_at"])
        except (TypeError, ValueError) as error:
            raise TaskError("contact_reminiscence_invalid", "reminiscence window timestamps are invalid") from error
        if (stamp(opened) != marker["opened_at"] or stamp(expires) != marker["expires_at"]
                or not opened <= at < expires):
            raise TaskError("contact_reminiscence_expired", "reminiscence opportunity is no longer current")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        preferences.require_contact(purpose)
