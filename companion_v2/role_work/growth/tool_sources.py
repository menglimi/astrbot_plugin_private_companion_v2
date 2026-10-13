"""Growth evidence handles resolve only to this turn's host-bound originals."""

import json

from companion_v2.conversation.foreground import PromptMaterial
from companion_v2.conversation.messages import event_from_document, source_from_document
from companion_v2.execution.models import TaskError, encode


class GrowthToolSources:
    def __init__(self, messages):
        self.messages = messages

    def offers(self, context, batch_id):
        from companion_v2.conversation.native_tool_sources import native_offers, native_turn
        if native_turn(batch_id):
            return native_offers(self.messages, context, batch_id)
        batch = self.messages.owned(context, batch_id)
        saved = json.loads(batch["contributions_json"])
        keys = saved.get("inputs", []) if isinstance(saved, dict) else []
        rows = self.messages.runtime.read_all(
            "SELECT * FROM conversation_inputs WHERE batch_id = ? ORDER BY position", (batch_id,))
        result = {}
        for row in rows:
            if row["event_key"] not in keys:
                continue
            if row["withdrawn"]:
                raise TaskError("message_withdrawn", "original growth evidence was withdrawn")
            event = event_from_document(json.loads(row["event_json"]), context)
            purpose = "current_source" if row["event_key"] == keys[0] else "merged_input:" + row["event_key"]
            result["growth-input-" + str(row["position"])] = (event.source, event.capability, purpose)
        for row in self.messages.runtime.read_all(
                "SELECT * FROM conversation_tool_sources WHERE batch_id = ? ORDER BY handle", (batch_id,)):
            result["growth-source:" + row["handle"]] = (
                source_from_document(json.loads(row["source_json"])), row["capability"], "host_offered_source")
        return result

    def material(self, context, batch_id):
        offers = self.offers(context, batch_id)
        return PromptMaterial("role.growth.tools", "growth_evidence_handles", encode([
            {"handle": handle, "purpose": value[2]} for handle, value in offers.items()]))

    def resolve(self, context, batch_id, handles, at):
        if (type(handles) is not list or not 1 <= len(handles) <= 8
                or any(type(handle) is not str for handle in handles) or len(set(handles)) != len(handles)):
            raise TaskError("growth_sources_invalid", "select one to eight original evidence handles")
        offers = self.offers(context, batch_id)
        references = []
        for handle in handles:
            if handle not in offers:
                raise TaskError("growth_source_unavailable", "growth evidence handle was not offered in this turn")
            source, capability, _ = offers[handle]
            if source.scope != context.scope:
                raise TaskError("growth_source_scope", "growth evidence belongs to another private scope")
            self.messages._read_source(source, context, capability, at)
            if source not in references:
                references.append(source)
        return tuple(references)
