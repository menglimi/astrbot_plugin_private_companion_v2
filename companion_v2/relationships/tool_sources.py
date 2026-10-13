"""Relationship proposals cite only originals offered by the current host turn."""

import json

from companion_v2.conversation.foreground import PromptMaterial
from companion_v2.conversation.messages import event_from_document, source_from_document
from companion_v2.execution.models import TaskError, encode


class RelationshipToolSources:
    def __init__(self, messages):
        self.messages = messages

    def offers(self, context, batch_id):
        from companion_v2.conversation.native_tool_sources import native_offers, native_turn
        if native_turn(batch_id):
            return native_offers(self.messages, context, batch_id)
        batch = self.messages.owned(context, batch_id)
        saved = json.loads(batch["contributions_json"])
        keys = saved.get("inputs", []) if isinstance(saved, dict) else []
        result = {}
        for row in self.messages.runtime.read_all(
                "SELECT * FROM conversation_inputs WHERE batch_id = ? ORDER BY position", (batch_id,)):
            if row["event_key"] not in keys:
                continue
            if row["withdrawn"]:
                raise TaskError("message_withdrawn", "original relationship evidence was withdrawn")
            event = event_from_document(json.loads(row["event_json"]), context)
            purpose = "current_source" if row["event_key"] == keys[0] else "merged_input:" + row["event_key"]
            result["relationship-input-" + str(row["position"])] = (event.source, event.capability, purpose)
        for row in self.messages.runtime.read_all(
                "SELECT * FROM conversation_tool_sources WHERE batch_id = ? ORDER BY handle", (batch_id,)):
            result["relationship-source:" + row["handle"]] = (
                source_from_document(json.loads(row["source_json"])), row["capability"], "host_offered_source")
        return result

    def material(self, context, batch_id):
        return PromptMaterial("relationship.memory.tools", "relationship_evidence_handles", encode([
            {"handle": handle, "purpose": value[2]} for handle, value in self.offers(context, batch_id).items()]))

    def resolve(self, context, batch_id, handles, at):
        if (type(handles) is not list or not 1 <= len(handles) <= 8
                or any(type(handle) is not str for handle in handles) or len(set(handles)) != len(handles)):
            raise TaskError("relationship_sources_invalid", "select one to eight original evidence handles")
        offered, references = self.offers(context, batch_id), []
        for handle in handles:
            if handle not in offered:
                raise TaskError("relationship_source_unavailable", "evidence handle was not offered in this turn")
            source, capability, _ = offered[handle]
            if source.scope != context.scope:
                raise TaskError("relationship_source_scope", "new proposals require this turn's private sources")
            self.messages._read_source(source, context, capability, at)
            if source not in references:
                references.append(source)
        return tuple(references)
