"""Read-only acquaintance tool exposed to authorized conversations."""

from companion_v2.execution.models import TaskError, encode
from companion_v2.model_gateway.models import ToolSpec
from companion_v2.conversation.addressing import ADDRESSING_INSTRUCTION


INSTRUCTION = (
    "current_person_card 和 acquaintance.recall 是本角色对成员的相识记录：display_name 只是称呼参考，"
    "来自管理员设定、本人陈述或平台资料，不证明对方自称的身份；计数只是观察统计，不代表亲疏、权限或私聊关系。"
    "称呼与熟悉程度不得超出记录；没有记录就按普通成员自然交流，不要假装认识。"
    + ADDRESSING_INSTRUCTION
)


class PersonAcquaintanceTools:
    actions = frozenset({"acquaintance.recall"})
    mutations = frozenset()

    def __init__(self, acquaintance):
        self.acquaintance = acquaintance
        self.catalog = ()
        if acquaintance is not None:
            self.catalog = (ToolSpec("acquaintance.recall",
                "查询本角色对当前或指定发言成员的相识记录（称呼参考与互动计数）。",
                encode({"type": "object",
                        "properties": {"speaker_id": {"type": "string",
                                                      "description": "成员原生账号，缺省为当前发言者"}},
                        "required": [], "additionalProperties": False})),)

    def catalog_for(self, context):
        if self.acquaintance is None or not self.acquaintance.available(context):
            return ()
        return self.catalog

    def execute(self, context, batch_id, call_id, action, arguments):
        if action not in self.actions:
            raise TaskError("acquaintance_action_unavailable", "this action is not exposed here")
        if type(arguments) is not dict or set(arguments) - {"speaker_id"}:
            raise ValueError("acquaintance tool fields do not match its contract")
        result = self.acquaintance.recall(context, arguments.get("speaker_id"))
        return {"state": "succeeded", "effect": "none", "payload": result}, None

    def validate(self, row, context, result):
        # Bot-internal derived state: a later counter bump does not invalidate
        # what this turn already saw, and the card carries no source of its own.
        return result, None
