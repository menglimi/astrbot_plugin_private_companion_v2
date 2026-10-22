"""Reference-only group memory snapshots and proof of changes made in this turn."""

from dataclasses import replace
import json

from companion_v2.conversation.foreground import ContextContribution, ContributionState, PromptMaterial
from companion_v2.execution.models import TaskError, encode
from .service import KIND, OWNER
from .access import owner_key


VERSION = "memory.group.context.v1"
MAX_ITEMS, MAX_BYTES = 4, 16384
INSTRUCTION = (
    "group_memory 是当前群、账号/Bot 与角色共用的群记忆，按原账号归因，记录某位成员当时的陈述或请求，不自动成为全群共识、已核实事实或当前发言者资料。保留原说法、时间和不确定性；自然接话，不播报账号，不与私聊资料混用或写进私人画像。只有内容有持续价值或成员明确要求保留时才调用 group.memory.remember，并用本轮真实 input_handle（group-input-1 是当前输入，后续编号按合并顺序）准确归因；每条写入须由所选原话独立支持，只有指代或需借他人旧话才能成立时先澄清，相反观点分别保留，不替别人修订或撤回。带图或引用的输入没有记忆写入句柄，可正常讨论，但不把图片解读、引用他人原话、[图片 N]/[语音 N]/[视频 N]/[合并转发 N]/[引用消息]占位符、标题或路由元数据当成本成员陈述、兴趣或记忆依据；兴趣候选不持久化为群记忆。成功回执只证明本地保存或撤回（撤回表示停止后续使用，不代表删除平台消息），不证明消息已送达；按真实查询与操作结果说明，记忆可能分页或受预算截断，未显示不等于没有。"
)


class GroupMemoryContext:
    def __init__(self, memory):
        self.memory = memory

    def capture(self, context, batch_id):
        snapshot = {"version": VERSION, "context_key": context.key, "batch_id": batch_id,
                    "available": True, "references": [], "partial": True}
        try:
            self.memory.access.check(context)
        except TaskError:
            return {**snapshot, "available": False}
        rows = self.memory.runtime.read_all("""SELECT view_id, revision FROM memory_views
            WHERE owner_key = ? AND kind = ? AND state = 'active' ORDER BY updated_at DESC, view_id DESC LIMIT 32""",
            (owner_key(context), KIND))
        used = 0
        for row in rows:
            try:
                item, _ = self.memory.read(context, row["view_id"], row["revision"])
            except TaskError:
                continue
            size = len(encode(item).encode("utf-8"))
            if used + size > MAX_BYTES:
                continue
            used += size
            snapshot["references"].append({"memory_id": row["view_id"], "revision": row["revision"]})
            if len(snapshot["references"]) == MAX_ITEMS:
                break
        return snapshot

    def contributions(self, snapshot, context, batch_id):
        if (type(snapshot) is not dict or set(snapshot) != {"version", "context_key", "batch_id", "available", "references", "partial"}
                or snapshot["version"] != VERSION or snapshot["context_key"] != context.key or snapshot["batch_id"] != batch_id
                or type(snapshot["references"]) is not list or len(snapshot["references"]) > 32
                or type(snapshot["available"]) is not bool or snapshot["partial"] is not True):
            raise TaskError("group_memory_snapshot_invalid", "memory snapshot must keep its original group batch")
        if not snapshot["available"]:
            if snapshot["references"]:
                raise TaskError("group_memory_snapshot_invalid", "unavailable memory cannot contain references")
            return ()
        self.memory.access.check(context)
        materials, seen, used = [], set(), 0
        for ref in snapshot["references"]:
            if type(ref) is not dict or set(ref) != {"memory_id", "revision"}:
                raise TaskError("group_memory_snapshot_invalid", "memory needs an exact ID and revision")
            item, source = self.memory.read(context, ref["memory_id"], ref["revision"])
            if item["memory_id"] in seen:
                raise TaskError("group_memory_snapshot_invalid", "memory references must be unique")
            seen.add(item["memory_id"])
            payload = encode(item)
            used += len(payload.encode("utf-8"))
            if used > MAX_BYTES:
                raise TaskError("group_memory_context_budget", "memory exceeded its original context budget")
            materials.append(ContextContribution("group-memory:" + item["memory_id"], OWNER, "group_memory",
                                                ContributionState.READY, payload, source, True))
        return tuple(materials)

    def after_write(self, context, batch_id, receipt):
        from companion_v2.conversation.native_tool_sources import native_turn
        if native_turn(batch_id):
            return
        row = self.memory.messages.batch(batch_id)
        saved = json.loads(row["contributions_json"])
        snapshot = saved.get("group_memory")
        if not snapshot or not snapshot["available"]:
            return
        # Only this turn's acknowledged target is removed. New text is presented
        # by the verified tool result; old unrelated references remain frozen.
        snapshot["references"] = [ref for ref in snapshot["references"] if ref["memory_id"] != receipt["memory_id"]]
        history = saved.get("group_context")
        if history is not None:
            replies = self.memory.messages.group_context.replies
            history["references"] = [ref for ref in history["references"]
                                     if not replies.depends_on_memory(ref, {receipt["memory_id"]})]
        with self.memory.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_batches SET contributions_json = ? WHERE batch_id = ?",
                               (encode(saved), batch_id))

    def validate_refresh(self, context, batch_id, original, request, old_history, history, tools,
                         *, optional_refresh=False):
        if len(history) < len(old_history):
            return False
        mutable = lambda m: m.owner == OWNER and m.purpose == "group_memory"
        rows = tools.messages.tools._rows(batch_id)
        semantic = getattr(tools.messages.tools, "semantic", None)
        slang_changed = semantic.changed_slang(batch_id) if semantic is not None else set()
        changed = set()
        for row in rows:
            if row["action"] in tools.mutations and row["state"] == "succeeded":
                result = self.memory.operation(context, row["operation_id"])
                changed.add(result["memory_id"])
        def fixed_material(material):
            if mutable(material) or material.purpose in ("actual_tool_results", "contextual_word_meanings"):
                return False
            if material.purpose == "group_conversation_history":
                item = json.loads(material.payload)
                if item["type"] == "confirmed_group_reply":
                    part = self.memory.runtime.read_one("SELECT * FROM conversation_parts WHERE part_id = ?", (item["part_id"],))
                    if part is None:
                        return True
                    groups = self.memory.messages.group_context
                    return not groups.replies.depends_on_memory(groups.reply_ref(part), changed)
            return True
        fixed = tuple(m for m in original.context.materials if fixed_material(m))
        if tuple(m for m in request.context.materials if fixed_material(m))[:len(fixed)] != fixed:
            return False
        expected = tuple(m for m in original.context.materials if mutable(m)
                         and json.loads(m.payload)["memory_id"] not in changed)
        if tuple(m for m in request.context.materials if mutable(m)) != expected:
            return False
        original_slang = tuple(m for m in original.context.materials if m.purpose == "contextual_word_meanings")
        expected_slang = []
        for material in original_slang:
            payload = json.loads(material.payload)
            items = [item for item in payload["items"] if item["id"] not in slang_changed]
            if items:
                expected_slang.append(replace(material, payload=encode({**payload, "items": items})))
        if tuple(m for m in request.context.materials if m.purpose == "contextual_word_meanings") != tuple(expected_slang):
            return False
        visible = [{"call_id": row["tool_call_id"], "action": row["action"], "result":
                    tools.messages.tools._validate_result(row, request, context, tools.messages.tasks.now())[0]}
                   for row in rows]
        expected_results = (PromptMaterial("conversation.tools", "actual_tool_results", encode(visible)),) if visible else ()
        if tuple(m for m in request.context.materials if m.purpose == "actual_tool_results") != expected_results:
            return False
        for old, new in zip(old_history, history):
            if old.call != new.call:
                return False
            if old != new:
                row = next((r for r in rows if r["tool_call_id"] == old.call.call_id), None)
                owner = semantic if semantic and old.call.action in semantic.actions else tools
                if row is None or encode(owner.validate(row, context, json.loads(row["result_json"]))[0]) != new.result_json:
                    return False
        for exchange in history:
            row = next((r for r in rows if r["tool_call_id"] == exchange.call.call_id), None)
            if row is None or encode(tools.messages.tools._validate_result(
                    row, request, context, tools.messages.tasks.now())[0]) != exchange.result_json:
                return False
        return bool(changed or slang_changed or len(history) > len(old_history) or optional_refresh)
