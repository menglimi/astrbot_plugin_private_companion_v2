"""Group-only role tools, immutable result verification and grounded source views."""

from dataclasses import replace
import json

from companion_v2.conversation.foreground import PromptMaterial
from companion_v2.execution.models import TaskError, encode, require
from companion_v2.model_gateway.models import ToolSpec
from .context import INSTRUCTION
from .service import OWNER


FIELDS = {
    "group.memory.query": ((), ("query", "cursor", "limit")),
    "group.memory.legacy.query": (("query",), ("material_kind", "cursor", "limit", "time_start", "time_end")),
    "group.memory.remember": (("input_handle", "statement"), ("memory_id", "expected_revision")),
    "group.memory.retract": (("input_handle", "memory_id", "expected_revision"), ()),
    "group.memory.operation": (("operation_id",), ()),
}


class GroupMemoryTools:
    actions = frozenset(FIELDS)
    mutations = frozenset({"group.memory.remember", "group.memory.retract"})

    def __init__(self, memory, legacy_memory=None):
        self.memory, self.messages = memory, memory.messages
        self.legacy_memory = legacy_memory
        descriptions = (
            "在本群当前角色记忆中按原话线索查询；返回原发言者及版本，可沿 next_cursor 续查。",
            "只读查询已映射到本群的 V1 历史资料；结果是历史记录，不是当前事实，也不能作为群记忆写入证据。",
            "保存本轮成员有来源的公开陈述；修订须提供本人原记录 ID 和当前版本。",
            "按本人当前明确请求撤回其原群记忆；不代其他成员撤回，不删除平台原话。",
            "查询本人原群记忆操作的持久回执，查不到或未知不等于未执行。",
        )
        self.catalog = tuple(ToolSpec(action, description, encode({"type": "object",
            "properties": {key: {"type": "integer" if key in ("limit", "expected_revision") else "string"}
                           for key in (*required, *optional)},
            "required": list(required), "additionalProperties": False}))
            for (action, (required, optional)), description in zip(FIELDS.items(), descriptions))

    def catalog_for(self, context):
        try:
            self.memory.access.check(context)
        except TaskError:
            return ()
        try:
            self.memory.access.check(context, "group.memory.write")
        except TaskError:
            catalog = tuple(t for t in self.catalog if t.action not in self.mutations)
        else:
            catalog = self.catalog
        return tuple(t for t in catalog
                     if t.action != "group.memory.legacy.query" or self.legacy_memory is not None)

    def execute(self, context, batch_id, call_id, action, arguments):
        if action not in {t.action for t in self.catalog_for(context)}:
            raise TaskError("group_memory_action_unavailable", "this group action is not authorized")
        required, optional = FIELDS[action]
        if type(arguments) is not dict or set(required) - set(arguments) or set(arguments) - set(required) - set(optional):
            raise ValueError("group memory tool fields do not match its contract")
        if action == "group.memory.query":
            result = self.memory.query(context, **arguments)
        elif action == "group.memory.legacy.query":
            query = self.legacy_memory.query.legacy
            result = require(query.query(context, query_intent=arguments["query"],
                material_kind=arguments.get("material_kind", "all"),
                cursor=arguments.get("cursor"), limit=arguments.get("limit"),
                time_start=arguments.get("time_start"), time_end=arguments.get("time_end"),
                group_read_authorized=True))
        elif action == "group.memory.operation":
            result = self.memory.operation(context, arguments["operation_id"])
        else:
            result = self.memory.change(context, batch_id, call_id,
                action="remember" if action == "group.memory.remember" else "retract", **arguments)
        operation = result.get("operation_id") if action in self.mutations else None
        return {"state": "succeeded", "effect": "committed" if operation else "none", "payload": result}, operation

    def validate(self, row, context, result):
        self.memory.access.check(context)
        if row["action"] not in self.actions:
            raise TaskError("group_action_unavailable", "a group cannot adopt private tool results")
        if row["state"] != "succeeded":
            return result, None
        later = self.messages.tools._rows(row["batch_id"])
        changed = set()
        for other in later:
            if other["sequence"] > row["sequence"] and other["action"] in self.mutations and other["state"] == "succeeded":
                changed.add(self.memory.operation(context, other["operation_id"])["memory_id"])
        payload, materials = result["payload"], []
        if row["action"] == "group.memory.query":
            items = payload["items"]
        elif row["action"] == "group.memory.legacy.query":
            if self.legacy_memory is None:
                raise TaskError("group_memory_tool_unavailable", "historical memory reader is unavailable")
            self.memory.access.check(context, "group.memory.read")
            self.legacy_memory.query.legacy.verify(context, payload["items"])
            return result, None
        else:
            identifier = (json.loads(row["arguments_json"])["operation_id"] if row["action"] == "group.memory.operation"
                          else row["operation_id"])
            if self.memory.operation(context, identifier) != payload:
                raise TaskError("group_memory_receipt_changed", "tool receipt must match the original operation")
            items = []
            if row["action"] == "group.memory.remember":
                if payload["memory_id"] in changed:
                    return {"state": "superseded", "effect": "committed", "operation_id": identifier}, None
                item, _ = self.memory.read(context, payload["memory_id"], payload["revision"])
                items = [item]
        if any(item["memory_id"] in changed for item in items):
            return {"state": "superseded", "effect": "none", "reason": "changed_by_this_turn"}, None
        for item in items:
            current, source = self.memory.read(context, item["memory_id"], item["revision"])
            if current != item:
                raise TaskError("group_memory_result_changed", "original query result no longer matches its source")
            materials.append(PromptMaterial(OWNER, "group_memory_tool:" + row["tool_call_id"], encode(item), source))
        return result, tuple(materials)

    def augment(self, batch, context, request, at):
        materials = list(request.context.materials)
        if self.catalog_for(context):
            materials.append(PromptMaterial(OWNER, "group_memory_input_handles",
                encode(list(self.memory.access.offered(context, batch["batch_id"])))))
        visible = []
        for row in self.messages.tools._rows(batch["batch_id"]):
            result, sources = self.messages.tools._validate_result(row, request, context, at)
            visible.append({"call_id": row["tool_call_id"], "action": row["action"], "result": result})
            if sources is not None:
                materials.extend(sources if isinstance(sources, tuple) else (sources,))
        if visible:
            materials.append(PromptMaterial("conversation.tools", "actual_tool_results", encode(visible)))
        return replace(request, context=replace(request.context, materials=tuple(materials)),
                       instruction=request.instruction + "\n" + INSTRUCTION)
