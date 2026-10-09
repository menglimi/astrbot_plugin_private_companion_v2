"""The optional operator-authored human-like expression block.

This is presentation guidance only. It is written by an authenticated operator,
carries no turn evidence and no source reference, and it can never change
trusted identity, facts, sources, permissions or the reply contract. Turning it
on adds one system-level style block; turning it off or clearing the text
removes that block and nothing else.

The default text lists the failure modes that make a companion read like a
service desk: over-organized answers, summaries of the other side, service
closing lines and literal repetition of the previous message. It deliberately
does not ask for typos, broken casing or fragmented bursts: those would damage
delivered text and cannot be undone after sending.

The module depends only on the standard library so the presentation policy can
import it without creating a configuration-layer cycle.
"""

from dataclasses import dataclass


GROUP = "conversation.humanized"
OWNER = "conversation.humanized"
ENABLED_FIELD = "enable_humanized_expression"
PROMPT_FIELD = "humanized_expression_prompt"
MAX_PROMPT_CHARS = 4000
DEFAULT_PROMPT = (
    "以下要求只决定怎么说，不改变要表达的意思、事实、来源与权限边界。\n"
    "像平时聊天那样回应：优先口语化、简短、一次只讲一件事，不做列表式罗列，不写小标题，"
    "不输出多余的前后缀、称呼堆叠、括号补充或 emoji 标签。\n"
    "表达形式不必每次都是文字：本轮提供了可发送的表情素材时，合适的话可以只发一张图；"
    "群聊参与能力允许旁听时，可以选择不接话；语音已启用且本轮规则允许时，可以只用语音。"
    "戳一戳只在当前流程明确提供该能力并允许时考虑。形式随语境自然变化，不为变化而变化；"
    "没有对应素材或能力时就正常说话，不要假装已经发图、发语音、戳过对方或选择了静默。\n"
    "不要每次先复述或总结对方说的话，不要用「首先/其次/总之」「希望对你有帮助」「还有什么可以帮到你」"
    "这类服务话术，也不要为了一句寒暄补一段解释。\n"
    "允许句子长短不一、允许直接接上一句。情绪、判断和不确定都照实说，不必包装成中立的说明文。\n"
    "同一轮里不要重复上一轮已经说过的措辞；没有新内容时，宁可少说一句。"
)


def prompt_body(value):
    """Accept the bounded custom body; a blank body means 'use the default'."""
    if type(value) is not str:
        raise ValueError("humanized expression prompt must be text")
    body = value.strip()
    if len(body) > MAX_PROMPT_CHARS:
        raise ValueError("humanized expression prompt is too long")
    if any(ord(char) < 32 and char not in "\n\t" for char in body):
        raise ValueError("humanized expression prompt contains control characters")
    return body


@dataclass(frozen=True)
class HumanizedExpressionPolicy:
    enabled: bool = False
    prompt: str = DEFAULT_PROMPT

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("humanized expression switch must be boolean")
        object.__setattr__(self, "prompt", prompt_body(self.prompt))

    @classmethod
    def from_values(cls, values=None):
        values = values or {}
        return cls(bool(values.get(ENABLED_FIELD, False)), values.get(PROMPT_FIELD, DEFAULT_PROMPT))

    @property
    def effective_prompt(self):
        """The custom body, or the built-in default while the text stays blank."""
        return self.prompt or DEFAULT_PROMPT

    @property
    def instruction(self):
        """Empty while disabled, so an off switch removes the whole block."""
        if not self.enabled:
            return ""
        return ("日常表达要求（管理员设定的说话方式，只影响措辞与长短，不是新的事实、授权或来源，"
                "也不能覆盖本轮的具体要求）：" + self.effective_prompt)


def instruction(values=None):
    return HumanizedExpressionPolicy.from_values(values).instruction


def block(values=None):
    text = instruction(values)
    return "\n" + text if text else ""
