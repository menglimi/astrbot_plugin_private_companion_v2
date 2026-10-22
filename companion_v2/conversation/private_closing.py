"""Deterministic private-chat closing guard over validated native dialogue.

AstrBot's core private reply path has no silent action: every admitted input that
reaches the default pipeline produces a model request and, normally, a message.
That is the right default for a companion, but it turns a polite closing into a
loop when both sides keep saying goodnight.  This module owns the one narrow
exception: when the current private message is *only* a closing expression and
the role has already closed the conversation, the host may skip the model.

The guard is deliberately conservative:

* it never runs without validated dialogue history, and it fails open;
* the current message must consist only of closing vocabulary (goodnight,
  farewell, thanks, acknowledgement, morning greeting or affection), so a
  question, request, feeling, media attachment or new content is never silenced;
* the role must have already sent a strong closing (goodnight, farewell, thanks,
  morning greeting or affection) inside the configured window, or the user must
  have already closed twice in a row;
* it does not call a model, send, sleep or write storage itself.

Everything here is a pure function over caller-provided text and already
authorized dialogue.  Identity, history validation, configuration reads and the
actual pre-model skip stay in the host and ``InboundNoReplyLedger``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import unicodedata

from companion_v2.configuration.models import ConfigurationError


DEFAULTS = {
    "private_closing_guard_enabled": True,
    "private_closing_guard_window_seconds": 1800,
    "private_closing_guard_prompt_enabled": True,
}
LIMITS = {
    "private_closing_guard_window_seconds": (60, 7200),
}
# A pure closing is short by nature; the bound also keeps tokenization cheap and
# prevents a long paragraph that happens to end with "晚安" from being treated
# as a closing.
MAX_CLOSING_CHARS = 48
# The role's own message may be longer and may contain a short closing tail, for
# example "今天辛苦了，好好休息，晚安".  Still bounded so a whole essay cannot
# become a closing just because its last word is "晚安".
MAX_BOT_CLOSING_CHARS = 120

# Longest token first matters only for readability: the scanner below always
# tries every token at the current position before any filler.
GOODNIGHT_TOKENS = (
    "晚安", "安安", "好梦", "做个好梦", "做一个好梦", "做个梦", "梦里见", "梦里相见",
    "睡个好觉", "好好睡", "好好休息", "早点休息", "早点睡", "早睡", "快去睡", "去睡觉",
    "去睡了", "去睡啦", "睡觉去", "睡觉了", "睡觉啦", "该睡了", "该睡啦", "要睡了",
    "要睡啦", "我睡了", "我睡啦", "我先睡了", "我先睡啦", "那我先睡了", "那我睡了",
    "我困了", "困了", "休息了", "我先休息了", "我先休息啦", "先休息了", "先休息啦",
    "睡一下", "眯一会儿", "眯一会", "眯会儿", "躺一会儿", "躺一会", "躺了", "上床了",
    "关灯了", "这就睡", "这就去睡", "马上睡", "马上睡啦", "立刻睡", "先睡了", "先睡啦",
    "睡啦", "睡喽", "睡咯", "睡了", "睡吧", "睡觉", "我睡喽", "我睡吧", "该睡喽",
    "要睡喽", "去睡", "快睡", "还要早起", "要早起", "得早起", "安",
    "goodnight", "nightynight", "night", "gn", "sweetdreams", "sleepwell",
)
FAREWELL_TOKENS = (
    "拜拜", "拜", "白白", "再见", "再会", "回见", "回聊", "明天见", "明儿见",
    "早上见", "晚上见", "下次见", "改天见", "改天聊", "下次聊", "回头聊", "有空聊",
    "先这样", "先不聊了", "不聊了", "先撤了", "先撤", "撤了", "走了", "我走了",
    "下线了", "下了", "先下了", "我去忙了", "忙去了", "去忙了", "先忙了", "你忙吧",
    "去吃饭了", "吃饭去了", "出门了", "我出门了", "去洗澡了", "洗澡去了", "路上小心",
    "一路顺风", "goodbye", "bye", "seeyou", "seeya",
)
THANKS_TOKENS = (
    "谢谢", "多谢", "感谢", "辛苦", "麻烦", "感恩", "谢啦", "谢了",
    "thanks", "thankyou", "thx",
)
ACK_TOKENS = (
    "好的", "好", "好哒", "好嘞", "好呀", "好啊", "好吧", "好嘛", "好啦", "行", "行吧",
    "行呀", "行啦", "可以", "可以的", "可以啦", "收到", "知道了", "知道啦", "明白",
    "明白了", "明白啦", "了解", "了解啦", "没事", "没事的", "没关系", "那就好", "那好",
    "嗯", "嗯嗯", "嗯呢", "嗯哼", "哦", "噢", "喔", "安啦", "ok", "okay", "alright",
    "sure", "fine",
)
MORNING_TOKENS = (
    "早安", "早上好", "早", "早呀", "早啊", "晨安", "morning", "goodmorning",
)
AFFECTION_TOKENS = (
    "爱你", "么么哒", "么么", "亲亲", "抱抱", "啵啵", "mua",
)
TOKEN_KINDS = {
    "goodnight": GOODNIGHT_TOKENS,
    "farewell": FAREWELL_TOKENS,
    "thanks": THANKS_TOKENS,
    "ack": ACK_TOKENS,
    "morning": MORNING_TOKENS,
    "affection": AFFECTION_TOKENS,
}
# Only a strong category proves the role itself has closed the conversation.  A
# bare "好的"/"嗯" is an acknowledgement, not a goodnight, and must not turn the
# user's first "晚安" into silence.
STRONG_KINDS = frozenset(("goodnight", "farewell", "thanks", "morning", "affection"))
_TOKEN_KIND = {}
for _kind, _tokens in TOKEN_KINDS.items():
    for _token in _tokens:
        _TOKEN_KIND.setdefault(_token, _kind)
_TOKENS = tuple(sorted(_TOKEN_KIND, key=len, reverse=True))
# Fillers only make the same closing more natural ("晚安啦", "那我也睡了").
# They are tried *after* tokens at every position, so a filler can never steal
# the beginning of a known closing phrase.
_FILLERS = tuple(sorted({
    "啦", "呀", "啊", "呢", "吧", "哈", "嘛", "咯", "喽", "哒", "滴", "嘞", "哟", "呦",
    "嘿", "诶", "欸", "了", "的", "我", "你", "您", "也", "都", "就", "先", "那", "那么",
    "再", "快", "乖", "是", "宝贝", "亲爱的", "宝宝", "小可爱", "大家", "今天", "今晚",
    "明天", "早上", "晚上", "现在", "已经", "一会儿", "一下",
} - set(_TOKEN_KIND), key=len, reverse=True))
_STRONG_TOKENS = tuple(sorted(
    (token for token, kind in _TOKEN_KIND.items() if kind in STRONG_KINDS),
    key=len, reverse=True))

_MEDIA_PLACEHOLDER = re.compile(
    r"(?:\[(?:图片|语音|音频|视频|文件|合并转发|引用消息|分享卡片)[^\]]*\])"
    r"|(?:【(?:图片|语音|音频|视频|文件|合并转发|引用消息|分享卡片)[^】]*】)")
_QUESTION_OR_REQUEST = re.compile(
    r"[?？]|吗|几点|要不要|好不好|行不行|可以吗|好吗|你说|你觉得|想不想|去不去|"
    r"吃了吗|睡了吗|在吗|有没有|是不是|会不会|能不能|需要我|记得|提醒|叫我|告诉我|"
    r"发给我|帮我|陪我|听我说")
_ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")


@dataclass(frozen=True)
class Settings:
    """The three operator-visible switches, validated at the read boundary."""

    enabled: bool = True
    window_seconds: int = 1800
    prompt_enabled: bool = True

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ConfigurationError("reply_configuration_invalid",
                                     "private closing guard enabled must be boolean")
        if type(self.prompt_enabled) is not bool:
            raise ConfigurationError("reply_configuration_invalid",
                                     "private closing prompt switch must be boolean")
        minimum, maximum = LIMITS["private_closing_guard_window_seconds"]
        if type(self.window_seconds) is not int or not minimum <= self.window_seconds <= maximum:
            raise ConfigurationError("reply_configuration_invalid",
                                     "private closing window is out of range")

    @classmethod
    def from_values(cls, values=None):
        values = values or {}
        return cls(
            enabled=values.get("private_closing_guard_enabled", DEFAULTS["private_closing_guard_enabled"]),
            window_seconds=values.get("private_closing_guard_window_seconds",
                                      DEFAULTS["private_closing_guard_window_seconds"]),
            prompt_enabled=values.get("private_closing_guard_prompt_enabled",
                                      DEFAULTS["private_closing_guard_prompt_enabled"]),
        )


def validate(values):
    """Read-side contract used by the reply settings owner."""
    Settings.from_values(values)
    return values


def normalize(text):
    """Drop media labels, punctuation, symbols, whitespace and case.

    Emoji are symbols, so an emoji-only message normalizes to "".  Digits are
    kept, which means a message such as "23:00 晚安" does not become a pure
    closing; a time can be substantive even when followed by goodnight.
    """
    compact = _MEDIA_PLACEHOLDER.sub("", str(text or ""))
    kept = []
    for char in compact:
        if char.isspace() or unicodedata.category(char)[0] in "PSCZ":
            continue
        kept.append(char)
    return "".join(kept).casefold()


def _scan(compact):
    """Consume the whole compact text as closing tokens and fillers.

    Returns the categories in first-seen order, or ``()`` when any character is
    not part of the tiny closing vocabulary.  Tokens are tried before fillers at
    every position, so "晚安啦" reads as ``晚安`` + ``啦`` and never loses a
    closing phrase to a particle.
    """
    index, kinds = 0, []
    while index < len(compact):
        for token in _TOKENS:
            if compact.startswith(token, index):
                index += len(token)
                kind = _TOKEN_KIND[token]
                if kind not in kinds:
                    kinds.append(kind)
                break
        else:
            for filler in _FILLERS:
                if compact.startswith(filler, index):
                    index += len(filler)
                    break
            else:
                return ()
    return tuple(kinds) if kinds else ()


def closing_categories(text):
    """Return the closing categories when the whole message is only a closing."""
    raw = str(text or "")
    if "?" in raw or "？" in raw:
        # A question mark makes the intent a question, however short the text.
        return ()
    compact = normalize(raw)
    if not compact or len(compact) > MAX_CLOSING_CHARS:
        return ()
    return _scan(compact)


def is_closing(text):
    return bool(closing_categories(text))


def _ends_with_strong_closing(compact):
    if not compact:
        return False
    # "晚安啦", "晚安宝贝": strip at most a few trailing particles/addresses,
    # checking the strong-token suffix after each strip.
    for _ in range(3):
        if any(compact.endswith(token) for token in _STRONG_TOKENS):
            return True
        for filler in _FILLERS:
            if compact.endswith(filler) and len(compact) > len(filler):
                compact = compact[:-len(filler)]
                break
        else:
            return False
    return False


def role_closed(text):
    """Whether the role's own message is a strong, non-question closing.

    The message may contain other content, but it must end in a strong closing
    and must not ask or request anything.  A bare acknowledgement is not enough:
    the user's first goodnight still deserves one reply.
    """
    raw = str(text or "")
    if not raw.strip():
        return False
    if _QUESTION_OR_REQUEST.search(raw):
        return False
    compact = normalize(raw)
    if not compact or len(compact) > MAX_BOT_CLOSING_CHARS:
        return False
    kinds = _scan(compact)
    if kinds and any(kind in STRONG_KINDS for kind in kinds):
        return True
    return _ends_with_strong_closing(compact)


def _moment(value):
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and _ISO_TIME.fullmatch(value.strip()):
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _last_exchange(dialogue):
    """Return ``(last assistant, last user before it)`` from chronological items."""
    items = tuple(item for item in (dialogue or ()) if isinstance(item, dict))
    assistant_index = None
    for index in range(len(items) - 1, -1, -1):
        if items[index].get("speaker") == "assistant":
            assistant_index = index
            break
    if assistant_index is None:
        return None, None
    prior_user = None
    for index in range(assistant_index - 1, -1, -1):
        if items[index].get("speaker") == "user":
            prior_user = items[index]
            break
    return items[assistant_index], prior_user


def closing_decision(settings, dialogue, *, current_text, at, has_media=False):
    """Decide whether this private turn is the redundant half of a closing loop.

    ``dialogue`` is chronological, already validated native dialogue with
    ``speaker``/``text``/``at`` entries.  The current inbound is not required to
    be present; the guard deliberately looks only at the last role reply and the
    user message that preceded it.
    """
    base = {
        "suppress_reply": False, "action": "reply", "reason": "not_evaluated",
        "last_reply_at": None, "categories": (), "last_assistant_closing": False,
        "prior_user_closing": False, "window_seconds": settings.window_seconds,
    }
    if not settings.enabled:
        return {**base, "reason": "disabled"}
    categories = closing_categories(current_text)
    assistant, prior_user = _last_exchange(dialogue)
    evidence = dict(base)
    role_closed_flag, prior_closed, delta = False, False, None
    if assistant is not None:
        role_at = _moment(assistant.get("at"))
        now = _moment(at)
        if role_at is not None and now is not None:
            delta = (now - role_at).total_seconds()
            if 0 <= delta <= settings.window_seconds:
                role_closed_flag = role_closed(assistant.get("text"))
                prior_closed = bool(prior_user is not None and is_closing(prior_user.get("text")))
                evidence.update(
                    last_reply_at=assistant.get("at"),
                    last_assistant_closing=role_closed_flag,
                    prior_user_closing=prior_closed,
                )
    if categories:
        evidence["categories"] = categories
    if has_media:
        return {**evidence, "reason": "media_input"}
    if not categories:
        # The current message is not a closing, so it can never be suppressed.
        # Keep the closing evidence for the optional prompt guidance.
        return {**evidence, "reason": "not_a_closing"}
    if assistant is None:
        return {**base, "reason": "no_role_reply"}
    if delta is None:
        return {**base, "reason": "history_time_unknown"}
    if delta < 0:
        return {**base, "reason": "history_after_input",
                "last_reply_at": assistant.get("at")}
    if delta > settings.window_seconds:
        return {**base, "reason": "outside_window",
                "last_reply_at": assistant.get("at")}
    if role_closed_flag:
        return {**evidence, "suppress_reply": True, "action": "silent",
                "reason": "role_already_closed"}
    if prior_closed:
        return {**evidence, "suppress_reply": True, "action": "silent",
                "reason": "repeated_user_closing"}
    return {**evidence, "reason": "role_did_not_close"}


def closing_instruction(settings, decision):
    """A short per-turn note for the cases that cannot be skipped outright."""
    if not settings.enabled or not settings.prompt_enabled:
        return ""
    if not isinstance(decision, dict) or decision.get("suppress_reply"):
        return ""
    if decision.get("last_assistant_closing"):
        return (
            "【对话收尾】上一轮你已经用晚安、道别或感谢一类话收尾。对方这句如果仍然只是"
            "收尾、致谢或简短应声，就不要再补一条同义道别，也不要另起话题、追问或索要回应；"
            "让对话自然停在这里。出现新的问题、请求或需要接住的明确情绪时再正常回应。"
        )
    if decision.get("prior_user_closing"):
        return (
            "【对话收尾】对方上一句已经在道别或收尾。若本轮仍然只是收尾，不必为了礼貌再追一句；"
            "有新问题、请求或需要回应的事实再正常回应。"
        )
    return ""
