"""Apply enabled semantic classifications as conversational advice only."""

from .contract import CONFIGURABLE_DECISION_FIELDS


GUIDANCE = {
    "turn_state": {
        "complete": "当前表达已完整。",
        "unfinished": "用户可能继续补充，避免抢答半句话。",
        "uncertain": "尚不能确定用户是否说完，结合上下文谨慎回应。",
    },
    "action": {
        "reply": "当前适合回应用户的表达。",
        "interject": "可以结合群聊语境自然加入，避免打断他人的交流。",
        "clarify": "请求仍缺少关键对象时，先提出简洁的澄清问题。",
    },
    "reply_intent": {
        "answer": "直接回答当前问题。", "acknowledge": "自然接住对方的表达。",
        "ask": "通过自然追问推动对话。", "comfort": "温和支持和安慰对方。",
        "explain": "清楚解释必要的原因或步骤。", "summarize": "归纳当前信息，避免重复。",
    },
    "reply_style": {
        "brief": "简洁回应，保留完成任务所需的信息。", "normal": "按自然对话长度回应。",
        "detailed": "补充有帮助的背景与要点。", "serious": "保持认真、清楚和克制。",
        "playful": "在关系与语境允许时轻松活泼。",
    },
    "reply_form": {
        "text": "适合文字回应。", "voice": "用户希望语音，能力可用时遵循该表达要求。",
        "text_voice": "用户希望文字和语音，能力可用时同时提供。",
        "image": "图片表达较合适，仅考虑本轮可用且获授权的图片能力。",
    },
    "segment_mode": {
        "single": "适合一个简短完整回应，不必拆成多条。",
        "natural": "不同要点可自然分开表达，具体分段遵循宿主配置。",
        "keep_together": "步骤、列表、引用或代码应保持完整，避免切断语义。",
    },
    "tool_need": {
        "none": "仅凭当前对话即可回应。", "memory": "必要时考虑已授权的记忆能力。",
        "vision": "可能需要理解当前图片或视频。", "tts": "用户希望使用已配置的语音能力。",
        "image": "可能需要已授权的生图或编辑图片能力。",
        "external": "可能需要本轮已注册且获授权的外部工具。",
    },
}


def decision_advice(result):
    """Disabled fields must never apply the parser's neutral defaults."""
    if result.get("status") != "ok" or not isinstance(result.get("decision"), dict):
        return {}, ""
    enabled = result.get("enabled_fields") or {}
    active = {name: value for name, value in result["decision"].items()
              if name in CONFIGURABLE_DECISION_FIELDS and enabled.get(name, True)}
    advice = " ".join(GUIDANCE[name].get(value, "") for name, value in active.items())
    return active, ("Laya 本轮语义判断：" + advice + " 分类是表达建议，不授权工具；具体执行遵循宿主配置。") if advice else ""
