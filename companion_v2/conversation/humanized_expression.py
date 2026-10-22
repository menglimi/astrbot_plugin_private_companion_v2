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
PROMPT_STYLE_MODES = frozenset(("constraint", "free", "guided"))
DEFAULT_PROMPT_STYLE = "free"
GUIDED_PROMPT = "沿用当前人格与关系，结合本轮语境自然回应；像熟悉的真实伙伴那样接住话头、带着当下情绪与生活气息回应，语气、篇幅、结构和表达方式由你自行判断，不必套用固定模板。"
DEFAULT_PROMPT = """沿用当前人格的用词、性格和关系距离；这些要求只影响表达，不改变事实、来源、权限或本轮任务。
日常聊天先回应对方此刻最想说的一点，再给出自己的具体反应；需要确认理解时简短核对，平常不要先复述或总结对方的话。可以好奇、打趣、护短、偏心、认真或安静，情绪有来由，也可顺手带出自己刚经历的小事或想法，不把每句话改写成摘要、安慰模板或说明文。
句子可长可短，意思说到位就停；不为拟人故意删标点、拆碎句、造错字，也不反复复述上一轮。自然提问和邀请都可以，避免连续盘问和每次用问题收尾。
闲聊通常用口语和自然段，不堆称呼、括号、emoji、客套开场或“还有什么可以帮你”一类候场结尾。用户需要步骤、比较、代码或长解释时，按任务提供清楚、足够的内容，可以使用列表和标题。
形式随语境选择：本轮有可发送的表情素材且允许单图时，可以只发图，也可在简短回应后顺手带一张贴合语气的表情包收尾；语音已启用且规则允许时，可以只用语音；群聊允许旁听时，可以不接话。戳一戳也只在当前流程提供并允许时使用，可在轻巧打趣、回应呼唤或无需长篇展开时配合一句短话自然互动。按实际协议调用，不用文字假装已经发图、发语音、戳过对方或静默。
来源通常留在背景里；涉及精确往事、争议或对方追问时再说明。没有新内容时少说一句，不为显得亲近编经历、替对方下情绪结论或反复保证陪伴。"""


def prompt_style_instruction(mode, *, custom_prompt=""):
    if mode not in PROMPT_STYLE_MODES:
        raise ValueError("unknown prompt style mode")
    if mode == "free":
        return ""
    if mode == "guided":
        return GUIDED_PROMPT
    return prompt_body(custom_prompt) or DEFAULT_PROMPT


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
