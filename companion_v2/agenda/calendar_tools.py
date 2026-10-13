"""Original-role calendar queries and attributed commands; human confirmation stays separate."""

import json

from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.model_gateway.models import ToolSpec
from companion_v2.role_work.growth.tool_sources import GrowthToolSources
from companion_v2.identity_policy.private_domain import source_ref
from .calendar import INSTRUCTION


class CalendarTools:
    actions = frozenset({"calendar.query", "calendar.command"})
    instruction = "\n" + INSTRUCTION + "\ncalendar.command 的 evidence_handles 使用本轮 growth_evidence_handles 的原材料。确认约定由人类管理端完成。"

    def __init__(self, calendar, messages):
        self.calendar, self.messages = calendar, messages
        self.sources = GrowthToolSources(messages)
        self.catalog = (
            ToolSpec("calendar.query", "查看当前角色日历；时间是计划，不是已发生经历。", encode({"type": "object",
                "properties": {"after_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                "additionalProperties": False})),
            ToolSpec("calendar.command", "新增、修改、取消计划或提议约定，设置期次例外或提醒；不替用户确认约定。", encode({
                "type": "object", "properties": {
                    "action": {"type": "string", "enum": ["create", "revise", "cancel", "exception", "remind"]},
                    "id": {"type": "string"}, "expected_revision": {"type": "integer", "minimum": 0},
                    "data": {"type": "object", "description": "create/revise: kind(role_plan/user_report/commitment), title, detail, schedule(anchor含时区/timezone_name/frequency/interval/count/fold/gap_policy), duration_minutes, presence(公开短状态)。exception: sequence,start(null取消此期次)。remind: sequence。"},
                    "evidence_handles": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8}},
                "required": ["action", "id", "expected_revision", "evidence_handles"], "additionalProperties": False})),
        )

    def catalog_for(self, context):
        result = []
        for tool in self.catalog:
            try:
                self.calendar.access.check(context, "calendar.read" if tool.action.endswith("query") else "calendar.write")
                result.append(tool)
            except TaskError:
                pass
        return tuple(result)

    def execute(self, context, batch_id, call_id, action, arguments):
        from companion_v2.conversation.native_tool_sources import validate_tool_turn
        validate_tool_turn(self.messages, context, batch_id)
        if action == "calendar.query":
            if set(arguments) - {"after_id", "limit"} or not 1 <= arguments.get("limit", 20) <= 20:
                raise ValueError("invalid calendar query")
            result = self.calendar.inventory(context, **{"limit": 20, **arguments})
            return {"state": "succeeded", "effect": "none", "payload": result}, None
        if (not {"action", "id", "expected_revision", "evidence_handles"}.issubset(arguments)
                or set(arguments) - {"action", "id", "expected_revision", "evidence_handles", "data"}):
            raise ValueError("invalid calendar command")
        if arguments["action"] == "accept":
            raise TaskError("calendar_confirmation_required", "an inferred tool call cannot accept for the user")
        sources = self.sources.resolve(context, batch_id, arguments["evidence_handles"], self.calendar.tasks.now())
        key = "calendar-tool-" + digest([batch_id, call_id])
        args = dict(identifier=arguments["id"], expected_revision=arguments["expected_revision"], operation_key=key)
        if arguments["action"] == "remind":
            result = self.calendar.remind(context, **args, **(arguments.get("data") or {}))
        else:
            result = self.calendar.command(context, **args, action=arguments["action"], data=arguments.get("data"), sources=sources)
        return {"state": "succeeded", "effect": "committed", "payload": result}, result["operation_id"]

    def validate(self, row, context, result, later):
        self.calendar.access.check(context, "calendar.read" if row["action"].endswith("query") else "calendar.write")
        originals = result["payload"]["items"] if row["action"] == "calendar.query" else [result["payload"]]
        changed = False
        for item in originals:
            current = self.calendar.read(context, item["id"])
            revision = item["revision"]
            original = self.calendar.records.version(context, item["id"], revision)
            self.calendar.access.evidence(context, original["sources"])
            if row["action"] == "calendar.query" and original != item:
                raise TaskError("calendar_result_changed", "original query contents changed")
            if row["action"] == "calendar.command":
                if self.calendar.records.receipt(context, item["operation_id"]) != {**item, "replayed": False}:
                    raise TaskError("calendar_receipt_changed", "original receipt differs")
            for follow in later:
                if follow["action"] != "calendar.command" or follow["state"] != "succeeded":
                    continue
                receipt = json.loads(follow["result_json"])["payload"]
                if receipt["id"] == item["id"]:
                    if self.calendar.records.receipt(context, receipt["operation_id"]) != {**receipt, "replayed": False}:
                        raise TaskError("calendar_receipt_changed", "intervening receipt differs")
                    if receipt["revision"] != revision + 1:
                        raise TaskError("calendar_changed", "intervening calendar change is outside this turn")
                    revision = receipt["revision"]
            if revision != current["revision"]:
                raise TaskError("calendar_changed", "original calendar item changed outside this turn")
            changed |= revision != item["revision"]
        if changed and row["action"] == "calendar.query":
            return {"state": "superseded", "effect": "none", "reason": "changed_by_this_turn"}, None
        return result, None

    def confirmed_dependencies(self, row, context, result, later):
        self.validate(row, context, result, later)
        items = result["payload"]["items"] if row["action"] == "calendar.query" else [result["payload"]]
        return tuple({source_ref(source) for item in items
                      for source in self.calendar.records.version(context, item["id"], item["revision"])["sources"]})
