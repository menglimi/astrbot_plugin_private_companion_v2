"""Authenticated member evidence and stable group ownership across conversations."""

import json

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.identity_policy.personas import PersonaDirectory


CAPABILITIES = frozenset({"group.memory.read", "group.memory.write"})


def owner_key(context):
    scope = context.scope
    # Native per-member sessions remain separate. A reset conversation can still
    # recall this group's durable statements under the same role and session.
    return group_owner_key(scope.installation_id, scope.platform, scope.bot_id, scope.account_id,
                           scope.native_scope_id, scope.session_id, context.role_binding.role)


def group_owner_key(installation_id, platform, bot_id, account_id, group_id, session_id, role):
    return digest(["memory.group.v1", installation_id, platform, bot_id,
                   account_id, group_id, session_id, role])


class GroupMemoryAccess:
    def __init__(self, messages):
        self.messages, self.tasks, self.runtime = messages, messages.tasks, messages.runtime

    def check(self, context, capability="group.memory.read", *, at=None):
        if capability not in CAPABILITIES or context.scope.kind is not ScopeKind.GROUP:
            raise TaskError("group_memory_context_required", "group memory requires its collective group context")
        at = at or self.tasks.now()
        self.messages.group_context.authorize(context, at)
        require(self.tasks.identity.authorize(context.actor, scope=context.scope, capability=capability, observed_at=at))
        return owner_key(context)

    def input(self, context, reference, *, at=None):
        return self._input_for_owner(owner_key(context), reference, at=at)

    def _input_for_owner(self, owner, reference, *, at=None):
        """Internal evidence reader after member or control-plane authorization."""
        from companion_v2.conversation.messages import event_from_document
        at = at or self.tasks.now()
        if isinstance(reference, dict) and reference.get("kind") == "native_input":
            from companion_v2.conversation.native_tool_sources import group_input
            return group_input(self.messages, owner, reference, at=at)
        if self.messages.group_context.reference_key(reference)[0] != "input":
            raise TaskError("group_memory_evidence_required", "group memory requires an authenticated member input")
        row = self.runtime.read_one("SELECT * FROM conversation_inputs WHERE event_key = ?", (reference["event_key"],))
        if row is None or row["withdrawn"] or self.messages.group_context.input_ref(row) != reference:
            raise TaskError("group_memory_evidence_unavailable", "original member input changed or was withdrawn")
        batch = self.messages.batch(row["batch_id"])
        original = TaskContext.restore(json.loads(batch["context_json"]))
        if (original.scope.kind is not ScopeKind.GROUP or owner_key(original) != owner
                or batch["origin_key"] != original.key
                or original.audience != group_audience(original.scope, original.actor.subject)):
            raise TaskError("group_memory_evidence_scope", "member evidence belongs to another collective owner")
        # Long-term recall does not replay an old task or adopt its old binding
        # revision. It still requires the original human and role to be valid.
        role = require(PersonaDirectory(self.runtime).resolve(original.scope, observed_at=at))
        if role.binding.role != original.role_binding.role:
            raise TaskError("group_memory_evidence_role", "the original source no longer belongs to this role")
        for capability in ("text", "group.memory.write"):
            require(self.tasks.identity.authorize(original.actor, scope=original.scope,
                                                  capability=capability, observed_at=at))
        event = event_from_document(json.loads(row["event_json"]), original)
        if (event.scoped_key != row["event_key"] or event.scope != original.scope
                or event.principal != original.actor.principal or event.capability != "text" or event.received_at > at
                or digest([event, original.key, batch["role_instruction"]]) != row["event_hash"]
                or any(getattr(event, name, ()) for name in ("images", "quotes", "forwards", "audios", "videos"))):
            raise TaskError("group_memory_evidence_changed", "the captured member input no longer matches")
        record = self.messages._read_source(event.source, original, "text", at)
        if (record.audience != original.audience or record.content_hash != event.input_hash
                or digest(record.payload) != event.input_hash):
            raise TaskError("group_memory_evidence_changed", "member evidence must retain its original audience and text")
        return record, original, event

    def offered(self, context, batch_id):
        from companion_v2.conversation.native_tool_sources import group_reference, input_row, native_turn
        if native_turn(batch_id):
            return {"group-input-native": group_reference(input_row(self.messages, context, batch_id))}
        batch = self.messages.batch(batch_id)
        if batch["origin_key"] != context.key:
            raise TaskError("group_memory_batch_unavailable", "input handles belong to the original speaker and batch")
        saved = json.loads(batch["contributions_json"])
        selected = saved.get("inputs", []) if isinstance(saved, dict) else []
        return {"group-input-" + str(index): self.messages.group_context.input_ref(row)
                for index, row in enumerate(self.runtime.read_all(
                    "SELECT * FROM conversation_inputs WHERE batch_id = ? AND withdrawn = 0 ORDER BY position",
                    (batch_id,)), 1) if row["event_key"] in selected
                and not any(json.loads(row["event_json"]).get(name) for name in ("images", "quotes", "forwards", "audios", "videos"))}

    def current_input(self, context, batch_id, handle):
        from companion_v2.conversation.native_tool_sources import native_turn
        if native_turn(batch_id):
            reference = self.offered(context, batch_id).get(handle)
            if reference is None:
                raise TaskError("group_memory_handle_unavailable", "use the current native member input handle")
            record, original, event = self.input(context, reference)
            if original.actor.subject != context.actor.subject:
                raise TaskError("group_memory_speaker_changed", "a member can only author their own statement")
            return reference, record, original, event
        batch = self.messages.batch(batch_id)
        if batch["state"] != "sealed":
            raise TaskError("group_memory_batch_closed", "new group memory writes require an active sealed reply")
        reference = self.offered(context, batch_id).get(handle)
        if reference is None:
            raise TaskError("group_memory_handle_unavailable", "use an original input handle from this turn")
        record, original, event = self.input(context, reference)
        if original.actor.subject != context.actor.subject:
            raise TaskError("group_memory_speaker_changed", "a member can only author their own statement")
        return reference, record, original, event
