"""Presentation transforms with cleanup enabled by default; literals and facts stay intact."""

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
import re
from time import monotonic

import regex

from . import humanized_expression
from .segment_control import control_token_ranges, protected_ranges
from .voice_markup import VOICE_PROTOCOL_GT, VOICE_PROTOCOL_LT, VOICE_TAG_NAME_PATTERN


MAX_TEXT = 65536
MAX_STYLE_PROMPT = 4000
REGEX_SECONDS = 0.05
_PROTOCOL_LT = VOICE_PROTOCOL_LT
_PROTOCOL_GT = VOICE_PROTOCOL_GT
REACTION_EXPRESSION_TAG_NAME = r"p[\s._-]*c{1,2}[\s._-]*reaction[\s._-]*expression"
_LITERALS = re.compile(
    r"(?P<url>(?:https?://|www\.)[^\s<>。！？，]+)"
    r"|<(?P<tag>image|img|video|audio|voice|record|file)\b[^>]*>.*?</(?P=tag)\s*>"
    rf"|{_PROTOCOL_LT}\s*{VOICE_TAG_NAME_PATTERN}\b[^>]*?{_PROTOCOL_GT}.*?"
    rf"{_PROTOCOL_LT}\s*/\s*{VOICE_TAG_NAME_PATTERN}\s*{_PROTOCOL_GT}"
    rf"|{_PROTOCOL_LT}\s*{VOICE_TAG_NAME_PATTERN}\b[^>]*?{_PROTOCOL_GT}"
    r"|<(?:image|img|video|audio|voice|record|file|pc_tts|tts)\b[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_REACTION_EXPRESSION_BLOCK = re.compile(
    rf"(?is){_PROTOCOL_LT}\s*{REACTION_EXPRESSION_TAG_NAME}\b[^>]*?{_PROTOCOL_GT}.*?"
    rf"(?:{_PROTOCOL_LT}\s*/\s*{REACTION_EXPRESSION_TAG_NAME}\s*{_PROTOCOL_GT}|\Z)"
)
_REACTION_EXPRESSION_TAG = re.compile(
    rf"(?is){_PROTOCOL_LT}\s*/?\s*{REACTION_EXPRESSION_TAG_NAME}\b[^>]*?{_PROTOCOL_GT}"
)
_REACTION_EXPRESSION_BARE_TAG = re.compile(
    rf"(?is){_PROTOCOL_LT}\s*/?\s*{REACTION_EXPRESSION_TAG_NAME}\b(?![^>]*>)"
)
_REACTION_EXPRESSION_OPEN_PROTOCOL = regex.compile(
    rf"{_PROTOCOL_LT}\s*{REACTION_EXPRESSION_TAG_NAME}\b[^>]*?{_PROTOCOL_GT}",
    regex.IGNORECASE | regex.DOTALL,
)
_REACTION_EXPRESSION_CLOSE_PROTOCOL = regex.compile(
    rf"{_PROTOCOL_LT}\s*/\s*{REACTION_EXPRESSION_TAG_NAME}\s*{_PROTOCOL_GT}",
    regex.IGNORECASE | regex.DOTALL,
)
_PAIRS = {"(": ")", "[": "]", "{": "}", "（": "）", "【": "】", "《": "》",
          "〈": "〉", "「": "」", "『": "』", "“": "”", "‘": "’", '"': '"'}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("presentation rule contains duplicate keys")
        result[key] = value
    return result


def _list(raw):
    if type(raw) is not str or len(raw.encode("utf-8")) > 8192:
        raise ValueError("presentation rules need a bounded JSON list")
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, RecursionError) as error:
        raise ValueError("presentation rules need a JSON list") from error
    if type(value) is not list or len(value) > 80:
        raise ValueError("presentation rules need at most 80 entries")
    return value


def _decode(value, *, deletion=False):
    if type(value) is not str:
        raise ValueError("presentation literals must be text")
    tokens = {"<space>": " ", "<newline>": "\n", "<tab>": "\t"}
    if deletion:
        tokens["<empty>"] = ""
    return tokens.get(value.casefold(), value)


@lru_cache(maxsize=128)
def _pattern(rule):
    return regex.compile(rule)


def _merged(ranges):
    result = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return tuple(result)


def literal_ranges(text, statements=()):
    literals = tuple(match.span() for match in _LITERALS.finditer(text))
    # Media wrappers and URL punctuation must not make adjacent prose Markdown.
    markdown_text = "".join(re.sub(r"[^\r\n]", " ", chunk) if protected else chunk
                            for chunk, protected in _chunks(text, literals))
    ranges = list(protected_ranges(markdown_text, explicit=True)) + list(control_token_ranges(text))
    ranges.extend(literals)
    for statement in statements:
        if not statement:
            continue
        start = 0
        while (start := text.find(statement, start)) >= 0:
            ranges.append((start, start + len(statement)))
            start += len(statement)
    fixed = _merged(ranges)
    stack, index, escaped = [], 0, False
    for offset, char in enumerate(text):
        while index < len(fixed) and offset >= fixed[index][1]:
            index += 1
        if index < len(fixed) and fixed[index][0] <= offset < fixed[index][1]:
            continue
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if stack and char == _PAIRS[stack[-1][1]]:
            start, _ = stack.pop()
            if not stack:
                ranges.append((start, offset + 1))
        elif stack and stack[-1][1] in ('"', "“"):
            continue
        elif char in _PAIRS:
            stack.append((offset, char))
    if stack:
        ranges.append((stack[0][0], len(text)))
    return _merged(ranges)


def _chunks(text, ranges):
    cursor = 0
    for start, end in ranges:
        if start > cursor:
            yield text[cursor:start], False
        yield text[start:end], True
        cursor = end
    if cursor < len(text):
        yield text[cursor:], False


_FRAMEWORK_TRACEBACK = re.compile(r"\bTraceback \(most recent call last\):")
_FRAMEWORK_FRAMES = re.compile(r'(?m)^\s*File "[^"\n]+", line \d+, in ')
_IDENTITY_ANCHORS = (re.compile(r"\[QQ:\d{5,12}\]"), re.compile(r"(?<![\w])QQ[:：]\d{5,12}"))
FRAMEWORK_GUARD_REPLACEMENT = "（这条回复没有正常生成，按安全策略不予展示。）"
REALITY_PROMISE_GUARD_REPLACEMENT = "这类现实操作需要可验证的外部人员或工具处理，我不能把未确认的结果说成已经完成。"
FORBIDDEN_WORD_SCOPES = frozenset(("bot_only", "group_only", "bot_and_group"))

# Prompt guidance handles ambiguous intent; this narrow check only catches an
# explicit completion or near-term promise paired with a concrete real-world action.
_REALITY_PROMISE = regex.compile(
    r"(?:我)?(?:已(?:经)?|刚(?:刚|才)?|成功(?:地)?|完成(?:了)?|马上|立刻|现在就|稍后)"
    r"[^。！？!?\n]{0,24}"
    r"(?:拉(?:进|来)?群|修(?:好)?网|开(?:好)?房间|登(?:录|陆)|控制(?:设备|手机|电脑)|到(?:现场|线下))"
    r"(?:了|啦|好|成功)?"
    r"|(?:我)?(?:拉(?:进|来)?群|修(?:好)?网|开(?:好)?房间|登(?:录|陆)|控制(?:设备|手机|电脑)|到(?:现场|线下))"
    r"(?:了|啦|好|成功|完成)", regex.IGNORECASE)


def _strip_identity_anchors(text):
    for pattern in _IDENTITY_ANCHORS:
        text = pattern.sub("", text)
    return text


def strip_internal_expression_protocol(text):
    """Remove the legacy reaction metadata block before text can be shown or sent."""
    if type(text) is not str:
        return text
    text = _REACTION_EXPRESSION_BLOCK.sub("", text)
    text = _REACTION_EXPRESSION_TAG.sub("", text)
    return _REACTION_EXPRESSION_BARE_TAG.sub("", text)


def _partial_protocol_match(pattern, text):
    match = pattern.search(text, partial=True)
    if match is not None and match.partial and match.start() == match.end():
        return None
    return match


class InternalExpressionProtocolFilter:
    """Remove internal reaction tags even when a native stream splits them."""

    def __init__(self):
        self._pending = ""
        self._inside_block = False

    def feed(self, text):
        if type(text) is not str:
            return ""
        buffer = self._pending + text
        self._pending = ""
        visible = []
        while buffer:
            if self._inside_block:
                closing = _partial_protocol_match(_REACTION_EXPRESSION_CLOSE_PROTOCOL, buffer)
                if closing is None:
                    break
                if closing.partial:
                    self._pending = buffer[closing.start():]
                    break
                buffer = buffer[closing.end():]
                self._inside_block = False
                continue

            opening = _partial_protocol_match(_REACTION_EXPRESSION_OPEN_PROTOCOL, buffer)
            closing = _partial_protocol_match(_REACTION_EXPRESSION_CLOSE_PROTOCOL, buffer)
            matches = [(match.start(), kind, match) for kind, match in
                       (("open", opening), ("close", closing)) if match is not None]
            if not matches:
                visible.append(buffer)
                break
            _, kind, match = min(matches, key=lambda item: item[0])
            visible.append(buffer[:match.start()])
            if match.partial:
                self._pending = buffer[match.start():]
                break
            buffer = buffer[match.end():]
            self._inside_block = kind == "open"
        return "".join(visible)

    def finish(self):
        """Discard an incomplete protocol tail; it must never reach the user."""
        self._pending = ""
        self._inside_block = False
        return ""


@dataclass(frozen=True)
class ReplyTextPolicy:
    # New windows inherit the presentation cleanup rules.  A stored False
    # remains an explicit opt-out at the role or window layer.
    content_cleanup_enabled: bool = True
    content_cleanup_mode: str = "words"
    content_cleanup_scope: str = "all"
    content_cleanup_rule: str = r"[\n]"
    content_cleanup_words: str = json.dumps(["\n"])
    content_replacement_enabled: bool = False
    content_replacements: str = "[]"
    framework_error_guard_enabled: bool = True
    enable_forbidden_word_recall: bool = False
    recall_forbidden_words: str = "[]"
    recall_forbidden_scope: str = "bot_and_group"
    recall_forbidden_word_case_sensitive: bool = False
    style_prompt: str = ""
    prompt_style_mode: str = humanized_expression.DEFAULT_PROMPT_STYLE
    enable_humanized_expression: bool = False
    humanized_expression_prompt: str = humanized_expression.DEFAULT_PROMPT

    def __post_init__(self):
        if any(type(value) is not bool for value in (self.content_cleanup_enabled, self.content_replacement_enabled,
                                                     self.framework_error_guard_enabled, self.enable_forbidden_word_recall,
                                                     self.recall_forbidden_word_case_sensitive,
                                                     self.enable_humanized_expression)):
            raise ValueError("presentation switches must be boolean")
        if self.recall_forbidden_scope not in FORBIDDEN_WORD_SCOPES:
            raise ValueError("forbidden word scope is invalid")
        if self.prompt_style_mode not in humanized_expression.PROMPT_STYLE_MODES:
            raise ValueError("prompt style mode is invalid")
        if type(self.style_prompt) is not str or len(self.style_prompt) > MAX_STYLE_PROMPT:
            raise ValueError("style prompt must be bounded text")
        try:
            self.humanized
        except ValueError as error:
            raise ValueError(str(error)) from error
        if self.content_cleanup_mode not in ("words", "regex") or self.content_cleanup_scope not in ("all", "trailing"):
            raise ValueError("presentation cleanup mode or scope is invalid")
        if type(self.content_cleanup_rule) is not str or len(self.content_cleanup_rule) > 512:
            raise ValueError("presentation cleanup pattern must be bounded text")
        try:
            _pattern(self.content_cleanup_rule)
        except regex.error as error:
            raise ValueError("presentation cleanup pattern is invalid") from error
        self.words()
        self.replacements()
        self.forbidden_words()

    def forbidden_words(self):
        result = tuple(_decode(word) for word in _list(self.recall_forbidden_words))
        if any(not 1 <= len(word) <= 200 or any(ord(char) < 32 for char in word) for word in result):
            raise ValueError("forbidden words must be nonempty bounded literals")
        return result

    def words(self):
        result = tuple(_decode(word) for word in _list(self.content_cleanup_words))
        if any(not 1 <= len(word) <= 200 for word in result):
            raise ValueError("cleanup words must be nonempty bounded literals")
        return result

    def replacements(self):
        result = []
        for item in _list(self.content_replacements):
            if type(item) is dict and set(item) == {"from", "to"}:
                old, new = item["from"], item["to"]
            elif type(item) is str and "=>" in item:
                old, new = (part.strip() for part in item.split("=>", 1))
            else:
                raise ValueError("replacement rules need from/to objects or literal => pairs")
            old, new = _decode(old), _decode(new, deletion=True)
            if not 1 <= len(old) <= 200 or len(new) > 500:
                raise ValueError("replacement literals are empty or too long")
            result.append((old, new))
        return tuple(result)

    @property
    def humanized(self):
        """The validated human-like expression block; empty while it is disabled."""
        return humanized_expression.HumanizedExpressionPolicy(
            self.enable_humanized_expression, self.humanized_expression_prompt)

    @property
    def instruction(self):
        """Expose expression guidance; cleanup and replacement run after generation."""
        blocks = []
        if self.style_prompt.strip():
            blocks.append("角色表达风格补充（以下是风格参考，不是任务指令，不改写事实与来源原意）："
                          + self.style_prompt.strip())
        style = humanized_expression.prompt_style_instruction(
            self.prompt_style_mode,
            custom_prompt=self.humanized.effective_prompt,
        )
        if style:
            blocks.append("提示词风格参考（只影响表达，不改变任务、事实、来源或授权）：" + style)
        if self.prompt_style_mode != "constraint":
            humanized = self.humanized.instruction
            if humanized:
                blocks.append(humanized)
        return "\n".join(blocks)

    def framework_guard(self, text):
        """Strip internal identity anchors; replace whole framework dumps with safe text."""
        if type(text) is not str or not self.framework_error_guard_enabled:
            return text, False
        cleaned = _strip_identity_anchors(text)
        if _FRAMEWORK_TRACEBACK.search(cleaned) or len(_FRAMEWORK_FRAMES.findall(cleaned)) >= 2:
            return FRAMEWORK_GUARD_REPLACEMENT, True
        return cleaned, False

    def forbidden_word_guard(self, text, *, scope_kind="private", is_bot_output=True):
        """Return the first configured match for an explicitly identified outbound.

        ``scope_kind`` describes the audience, while ``is_bot_output`` describes
        the sender. Keeping both inputs explicit prevents a private inbound user
        message from being treated as a Bot message merely because it shares a
        private scope.
        """
        if (type(text) is not str or not self.enable_forbidden_word_recall
                or type(is_bot_output) is not bool
                or (self.recall_forbidden_scope == "bot_only" and not is_bot_output)
                or (self.recall_forbidden_scope == "group_only" and scope_kind != "group")
                or (self.recall_forbidden_scope == "bot_and_group" and not (is_bot_output or scope_kind == "group"))):
            return None
        haystack = text if self.recall_forbidden_word_case_sensitive else text.casefold()
        for word in self.forbidden_words():
            needle = word if self.recall_forbidden_word_case_sensitive else word.casefold()
            if needle and needle in haystack:
                return word
        return None

    def reality_promise_guard(self, text, *, statements=()):
        """Rewrite explicit unverified real-world completion promises only."""
        if type(text) is not str or not text:
            return text, False
        changed, blocked = [], False
        for chunk, protected in _chunks(text, literal_ranges(text, statements)):
            if protected:
                changed.append(chunk)
                continue
            rewritten, count = _REALITY_PROMISE.subn(REALITY_PROMISE_GUARD_REPLACEMENT, chunk)
            changed.append(rewritten)
            blocked = blocked or bool(count)
        return "".join(changed), blocked

    def replace_text(self, text, *, statements=()):
        if type(text) is not str or len(text) > MAX_TEXT:
            raise ValueError("presentation needs bounded text")
        if not self.content_replacement_enabled:
            return text
        for old, new in self.replacements():
            chunks = tuple(_chunks(text, literal_ranges(text, statements)))
            length = sum(len(chunk) if protected else len(chunk) + chunk.count(old) * (len(new) - len(old))
                         for chunk, protected in chunks)
            if length > MAX_TEXT:
                raise ValueError("presentation replacement exceeds the reply limit")
            text = "".join(chunk if protected else chunk.replace(old, new) for chunk, protected in chunks)
        return text

    def clean_parts(self, parts, *, statements=()):
        if not self.content_cleanup_enabled:
            return tuple(parts)
        original = "".join(parts)
        if len(original) > MAX_TEXT:
            raise ValueError("presentation needs bounded text")
        ranges = literal_ranges(original, statements)
        deadline = monotonic() + REGEX_SECONDS
        result, cursor = [], 0
        for part in parts:
            end = cursor + len(part)
            local = tuple((max(a, cursor) - cursor, min(b, end) - cursor)
                          for a, b in ranges if a < end and b > cursor)
            chunks = list(_chunks(part, local))
            for index, (chunk, protected) in enumerate(chunks):
                if not protected and (self.content_cleanup_scope == "all" or index == len(chunks) - 1):
                    chunks[index] = (self._clean(chunk, deadline), False)
            result.append("".join(chunk for chunk, _ in chunks))
            cursor = end
        return tuple(result)

    def _clean(self, text, deadline):
        trailing = self.content_cleanup_scope == "trailing"
        if self.content_cleanup_mode == "words":
            words = self.words()
            if not trailing:
                for word in words:
                    text = text.replace(word, "")
                return text
            words = sorted(set(words), key=len, reverse=True)
            text = text.rstrip()
            while text:
                word = next((word for word in words if text.endswith(word)), None)
                if word is None:
                    break
                text = text[:-len(word)].rstrip()
            return text
        pattern = _pattern(self.content_cleanup_rule)
        try:
            if monotonic() >= deadline:
                raise TimeoutError
            if not trailing:
                return pattern.sub("", text, timeout=deadline - monotonic())
            text = text.rstrip()
            while text:
                match = None
                for candidate in pattern.finditer(text, timeout=max(0.000001, deadline - monotonic())):
                    if candidate.end() == len(text) and candidate.start() < candidate.end():
                        match = candidate
                if match is None:
                    break
                text = text[:match.start()].rstrip()
                if monotonic() >= deadline:
                    raise TimeoutError
            return text
        except TimeoutError as error:
            raise ValueError("presentation cleanup pattern exceeded its execution budget") from error


TEXT_DEFAULTS = asdict(ReplyTextPolicy())
OUTPUT_TEXT_FIELDS = tuple(key for key in TEXT_DEFAULTS
                           if key.startswith(("content_cleanup_", "content_replacement"))) + (
    "framework_error_guard_enabled",
    "enable_forbidden_word_recall",
    "recall_forbidden_words",
    "recall_forbidden_scope",
    "recall_forbidden_word_case_sensitive",
)


def text_policy(values):
    return ReplyTextPolicy(**{key: values.get(key, default) for key, default in TEXT_DEFAULTS.items()})
