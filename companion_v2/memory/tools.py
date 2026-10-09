"""The original role's internal tool adapter. Host identity is never an argument."""

import json

from companion_v2.conversation.foreground import PromptMaterial
from companion_v2.execution.models import TaskError, encode, require
from companion_v2.model_gateway.models import ToolSpec

from . import codec
from .models import AtomRef, Proposal, owner_key
from .prompts import MEMORY_INSTRUCTION


ACTIONS = {
    "memory.query": ("memory.read", ("query_intent",), ("namespace", "kind", "limit", "cursor", "time_start", "time_end", "subjects", "at_time")),
    "memory.legacy.query": ("memory.read", ("query_intent",), ("material_kind", "limit", "cursor", "time_start", "time_end")),
    "memory.sources": ("memory.read", ("handle",), ("start", "max_chars")),
    "memory.proposal.submit": ("memory.propose", ("proposal",), ()),
    "memory.operation.get": ("memory.read", ("operation_id",), ()),
    "memory.forget": ("memory.forget", ("atom_id", "expected_revision", "evidence_handles"), ()),
    "memory.query.status": ("memory.read", (), ()),
    "memory.experience.save": ("memory.propose", ("view_id", "expected_revision", "title", "statements"), ("entities", "links", "occurred_at")),
}
MUTATIONS = frozenset({"memory.proposal.submit", "memory.forget", "memory.experience.save"})

PROPOSAL_PROPERTIES = {
    **{k: {"type": "string"} for k in ("operation", "namespace", "subject", "predicate", "object", "representation", "polarity", "attribution", "retention", "reason", "stability_estimate", "purpose", "visibility", "context_mode")},
    "evidence_handles": {"type": "array", "items": {"type": "string"}, "maxItems": 32},
    "qualifiers": {"type": "object", "additionalProperties": {"type": "string"}},
    "target_atom_id": {"type": "string"}, "expected_revision": {"type": "integer", "minimum": 1},
    "valid_from": {"type": ["string", "null"]}, "valid_to": {"type": ["string", "null"]},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "single_value": {"type": "boolean"}, "defer_until_boundary": {"type": "boolean"},
}
PROPOSAL_PROPERTIES["operation"] = {"enum": ["add", "correct", "retract", "no_op"]}
PROPOSAL_PROPERTIES["context_mode"] = {"enum": ["relevant", "pinned"]}
PROPOSAL_SCHEMA = {"type": "object", "properties": PROPOSAL_PROPERTIES, "required": ["operation", "evidence_handles"], "additionalProperties": False}


def decode_proposal(query, context, session_id, value):
    if type(value) is not dict or set(value) - set(PROPOSAL_PROPERTIES) or not {"operation", "evidence_handles"}.issubset(value):
        raise ValueError("proposal fields do not match the registered internal profile")
    data = dict(value)
    handles = data.pop("evidence_handles")
    if not isinstance(handles, list) or len(handles) > 32 or any(type(h) is not str for h in handles):
        raise ValueError("evidence handles must be a bounded list")
    target = data.pop("target_atom_id", None)
    revision = data.pop("expected_revision", None)
    if (target is None) != (revision is None):
        raise ValueError("target requires both ID and revision")
    return Proposal(**data, target=AtomRef(target, revision) if target else None,
                    evidence=tuple(query.resolve(context, session_id, h) for h in dict.fromkeys(handles)))


class MemoryTools:
    instruction = MEMORY_INSTRUCTION
    actions = frozenset(ACTIONS)

    def __init__(self, memory, messages):
        self.memory, self.messages = memory, messages
        self.catalog = tuple(ToolSpec(action,
            {"memory.query": "按人物、事件、时间、物件或原话线索查询已有事实、经历或原文。未命中不代表未发生。kind=facts/sources/experiences/all。",
             "memory.legacy.query": "只读查询已映射的 V1 历史记忆或时间线；结果是历史资料，不是当前事实，也不能作为记忆写入证据。",
             "memory.sources": "读取本轮真实来源 handle，可用 start/max_chars 续读相邻上下文。",
             "memory.proposal.submit": "提交有来源的记忆提议，明确纠正及时提交；其他待整理认识可设 defer_until_boundary。",
             "memory.operation.get": "核对原记忆操作回执；查不到不能证明未执行。",
             "memory.forget": "依用户请求逻辑遗忘明确记忆及派生使用，不声称物理删除日志。",
             "memory.query.status": "回看本轮实际读过的来源片段及剩余查询预算。",
             "memory.experience.save": "保存有来源的经历摘要，每个 statements 项为 text、evidence_handles、atoms（atom_id/revision）三项。entities 为本地人物或物件标签，links 为 view_id/revision/relation，不能绑定平台身份。"}[action],
            encode({"type": "object", "properties": {k: PROPOSAL_SCHEMA if k == "proposal" else {} for k in (*required, *optional)},
                    "required": list(required), "additionalProperties": False}))
            for action, (_, required, optional) in ACTIONS.items())

    def catalog_for(self, context):
        available = []
        for tool in self.catalog:
            try:
                self.memory.writer.access.check(context)
                self.memory.writer.access.check(context, ACTIONS[tool.action][0])
            except TaskError:
                continue
            available.append(tool)
        return tuple(available)

    def execute(self, context, batch_id, call_id, action, arguments, *, prepared=None):
        permission, required, optional = ACTIONS[action]
        if type(arguments) is not dict or not set(required).issubset(arguments) or set(arguments) - set(required) - set(optional):
            raise ValueError("memory tool arguments do not match the registered profile")
        self.memory.writer.access.check(context, permission)
        session_id = "memory:" + batch_id
        self.memory.query._session(context, session_id)
        writer, query = self.memory.writer, self.memory.query
        key = batch_id + ":" + call_id
        if action == "memory.query":
            result = require(query.query(context, session_id, **arguments, **(prepared or {})))
        elif action == "memory.legacy.query":
            result = require(query.legacy_materials(context, session_id, **arguments))
        elif action == "memory.sources":
            result = require(query.source(context, session_id, **arguments))
        elif action == "memory.proposal.submit":
            item = decode_proposal(query, context, session_id, arguments["proposal"])
            result = require(writer.submit(context, item, operation_key=key))
        elif action == "memory.forget":
            handles = arguments["evidence_handles"]
            if not isinstance(handles, list) or not 1 <= len(handles) <= 32:
                raise ValueError("forget requires bounded evidence handles")
            result = require(writer.forget(context, AtomRef(arguments["atom_id"], arguments["expected_revision"]),
                evidence=tuple(query.resolve(context, session_id, h) for h in handles), operation_key=key))
        elif action == "memory.operation.get":
            result = require(writer.operation(context, arguments["operation_id"]))
        elif action == "memory.experience.save":
            data = dict(arguments)
            statements = data.pop("statements")
            if type(statements) is not list or not 1 <= len(statements) <= 32:
                raise ValueError("experience statements must be bounded")
            decoded = []
            for statement in statements:
                if type(statement) is not dict or set(statement) != {"text", "evidence_handles", "atoms"}:
                    raise ValueError("each statement needs text, evidence_handles and atoms")
                if type(statement["atoms"]) is not list or len(statement["atoms"]) > 32 or type(statement["evidence_handles"]) is not list or len(statement["evidence_handles"]) > 32:
                    raise ValueError("statement evidence exceeds the budget")
                decoded.append({"text": statement["text"], "evidence": tuple(query.resolve(context, session_id, h) for h in statement["evidence_handles"]),
                                "atoms": tuple(AtomRef(**ref) for ref in statement["atoms"])})
            for field in ("entities", "links"):
                if field in data:
                    if type(data[field]) is not list:
                        raise ValueError("experience navigation must be a list")
                    data[field] = tuple(data[field])
            result = require(self.memory.experiences.save(context, statements=tuple(decoded), operation_key=key, **data))
        else:
            result = require(query.status(context, session_id))
        receipt = result.get("operation_id") if action in MUTATIONS else None
        if receipt:
            self.memory.context.after_write(batch_id, context, result)
        return {"state": "succeeded", "effect": "committed" if receipt else "none", "payload": result}, receipt

    def _durable_evidence(self, context, session_id, handle):
        """Check a captured tool dependency without extending the old query session."""
        stored = self.memory.runtime.read_one(
            """SELECT h.evidence_json FROM memory_handles h
               JOIN memory_sessions s ON s.session_id = h.session_id
               WHERE h.handle = ? AND h.session_id = ? AND s.owner_key = ? AND s.context_key = ?""",
            (handle, session_id, owner_key(context), context.key),
        )
        if stored is None:
            raise TaskError("memory_source_unavailable", "original reply evidence is unavailable")
        evidence = codec.evidence(json.loads(stored["evidence_json"]))
        self.memory.writer.access.evidence(context, evidence)
        return evidence

    def confirmed_dependencies(self, row, context, result, later):
        """Durable source provenance for a reply already confirmed by Delivery."""
        visible, materials = self.validate(row, context, result, later, durable=True)
        if visible["state"] != "succeeded":
            return ()
        sources = [item.source for item in materials or () if item.source is not None]
        payload = visible["payload"]
        if row["action"] == "memory.query":
            for item in payload["items"]:
                if item["kind"] == "fact":
                    fact = require(self.memory.writer.read(context, AtomRef(item["atom_id"], item["revision"]),
                        at=json.loads(row["arguments_json"]).get("at_time")))
                    sources.append(codec.source(fact["source"]))
                    handles = item["sources"]
                elif item["kind"] == "experience":
                    view = require(self.memory.experiences.read(context, item["view_id"], expected_revision=item["revision"]))
                    sources.append(codec.source(view["source"]))
                    handles = [handle for statement in item["statements"] for handle in statement["sources"]]
                else:
                    handles = [item["handle"]]
                sources.extend(self._durable_evidence(context, "memory:" + row["batch_id"], h).source for h in handles)
        return tuple(set(sources))

    def validate(self, row, context, result, later, *, durable=False):
        self.memory.writer.access.check(context, ACTIONS[row["action"]][0])
        if result["state"] != "succeeded":
            return result, None
        session_id = "memory:" + row["batch_id"]
        resolve = self._durable_evidence if durable else self.memory.query.resolve
        payload = result["payload"]
        changed_here = set()
        for other in later:
            if other["action"] in MUTATIONS and other["state"] == "succeeded":
                receipt = json.loads(other["result_json"])["payload"]
                if receipt.get("state") == "persisted" and receipt.get("atom_id"):
                    changed_here.add(receipt["atom_id"])
        materials = []
        if row["action"] == "memory.query":
            for item in payload["items"]:
                if item["kind"] == "fact":
                    if item["atom_id"] in changed_here:
                        return {"state": "superseded", "effect": "none", "reason": "changed_by_this_turn"}, None
                    require(self.memory.writer.read(context, AtomRef(item["atom_id"], item["revision"]),
                        at=json.loads(row["arguments_json"]).get("at_time")))
                    handles = item["sources"]
                elif item["kind"] == "experience":
                    require(self.memory.experiences.read(context, item["view_id"], expected_revision=item["revision"]))
                    handles = [h for s in item["statements"] for h in s["sources"]]
                else:
                    handles = [item["handle"]]
                for handle in handles:
                    resolve(context, session_id, handle)
        elif row["action"] == "memory.legacy.query":
            self.memory.query.legacy.verify(context, payload["items"])
        elif row["action"] == "memory.sources":
            evidence = resolve(context, session_id, payload["handle"])
            raw = self.memory.writer.access.evidence(context, evidence)
            if raw != payload["text"]:
                raise TaskError("memory_source_changed", "original source result changed")
            materials.append(PromptMaterial("memory.sources", "memory_source:" + row["tool_call_id"], raw, evidence.source))
        elif row["action"] in MUTATIONS:
            require(self.memory.writer.operation(context, payload["operation_id"]))
        return result, tuple(materials) if materials else None
