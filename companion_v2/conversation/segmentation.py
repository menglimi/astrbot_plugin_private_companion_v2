"""Deterministic reply segmentation shared by streamed and complete replies."""

from dataclasses import dataclass
import hashlib
import json
import math
import re

import regex

from .segment_control import LLM_SEGMENT_MARKER, controlled_parts, protected_ranges
from .text_processing import literal_ranges


DEFAULT_SPLIT_WORDS = ("。", "？", "！", "~", "～", "?", ".", "!", ";", "；", "……", "）", "“", "…")
DEFAULT_RULE_REGEX = r"(?<=[。！？!?…~～])\s*|\n+"
PART_GAP_MODES = frozenset(("fixed", "random", "log"))
_SOFT_COMMA_CHARS = frozenset((",", "，"))
_SOFT_COMMA_MIN_CHARS = 10


def part_gap_seconds(settings, text, seed):
    """Resolve one stable inter-part delay from the sealed reply settings."""
    mode = settings.get("part_gap_mode", "fixed")
    if mode == "fixed":
        return settings.get("part_gap_ms", 0) / 1000
    lower = settings.get("part_gap_min_ms", 1500) / 1000
    upper = settings.get("part_gap_max_ms", 3500) / 1000
    entropy = hashlib.sha256(str(seed).encode("utf-8")).digest()
    fraction = int.from_bytes(entropy[:8], "big") / ((1 << 64) - 1)
    if mode == "random":
        return lower + (upper - lower) * fraction
    if mode == "log":
        base = settings.get("part_gap_log_base", 2.1)
        characters = (len(text.split()) if all(ord(char) < 128 for char in text)
                      else sum(char.isalnum() for char in text))
        nominal = math.log(characters + 1, base)
        return min(60.0, max(0.1, nominal + fraction * 0.5))
    raise ValueError("part spacing mode is invalid")


def minimum_part_gap_seconds(settings, text):
    """The lower bound shown by offline previews for one inter-part delay."""
    mode = settings.get("part_gap_mode", "fixed")
    if mode == "fixed":
        return settings.get("part_gap_ms", 0) / 1000
    if mode == "random":
        return settings.get("part_gap_min_ms", 1500) / 1000
    if mode == "log":
        base = settings.get("part_gap_log_base", 2.1)
        characters = (len(text.split()) if all(ord(char) < 128 for char in text)
                      else sum(char.isalnum() for char in text))
        return min(60.0, max(0.1, math.log(characters + 1, base)))
    raise ValueError("part spacing mode is invalid")
_WIDTH_VARIANTS = (
    (",", "，"), (".", "．", "。"), ("?", "？"), ("!", "！"), (";", "；"),
    (":", "："), ("~", "～"), ("(", "（"), (")", "）"), ("[", "［"),
    ("]", "］"), ("{", "｛"), ("}", "｝"), ("<", "＜"), (">", "＞"),
    ('"', "＂"), ("'", "＇"), ("/", "／"), ("\\", "＼"), ("|", "｜"),
    ("+", "＋"), ("-", "－", "—"), ("=", "＝"), ("*", "＊"), ("&", "＆"),
    ("%", "％"), ("#", "＃"), ("@", "＠"), ("$", "＄"), ("^", "＾"),
    ("_", "＿"),
)
_FILE_SUFFIX = re.compile(
    r"(?i)(?<=[\w\u3400-\u9fff\u3040-\u30ff])\."
    r"(?:7z|aac|apk|avif|avi|bmp|bz2|com|css|csv|docx?|dmg|epub|exe|flac|"
    r"gif|gz|heic|heif|html?|ico|ini|ipa|jar|jpe?g|js|jsonl?|log|m4a|"
    r"m4v|md|mkv|mobi|mov|mp3|mp4|mpeg|mpg|msi|odt|ogg|opus|pdf|png|"
    r"pptx?|psd|py|rar|raw|rmvb|rtf|svg|tar|tgz|tiff?|toml|ts|txt|"
    r"wav|webm|webp|wmv|wma|xlsx?|xml|xz|ya?ml|zip)(?![\w])"
)


def _width_words(words):
    expanded = list(words)
    for variants in _WIDTH_VARIANTS:
        widths = {len(word) for word in words if word and word == word[0] * len(word)
                  and word[0] in variants}
        for width in sorted(widths):
            expanded.extend(char * width for char in variants)
    return tuple(sorted(set(expanded), key=lambda word: (-len(word), word)))


def _match_word(text, position, words):
    return next((word for word in words if text.startswith(word, position)), None)


def _is_punctuation_word(word):
    """Return whether a configured boundary token contains punctuation only."""
    return bool(word) and all(not char.isalnum() and not char.isspace() for char in word)


def _coalesce_punctuation_boundaries(text, boundaries):
    """Keep a run such as ``...？`` in one message boundary."""
    result = []
    for end in boundaries:
        if (result and end > result[-1]
                and text[result[-1]:end]
                and all(not char.isalnum() and not char.isspace()
                        for char in text[result[-1]:end])):
            result[-1] = end
        else:
            result.append(end)
    return tuple(result)


def _word_boundaries(text, words, protected):
    boundaries = []
    position = interval = 0
    while position < len(text):
        # A protected interval keeps every position inside it atomic, including
        # the position at its end: a paragraph the reader already retained must
        # not be split by a delimiter that happens to sit exactly on that edge.
        while interval < len(protected) and position > protected[interval][1]:
            interval += 1
        if interval < len(protected) and protected[interval][0] <= position:
            # A configured opening quote may separate the lead-in from an
            # otherwise atomic quoted title; content within stays protected.
            if text[position] == "“" and "“" in words and protected[interval][0] == position:
                boundaries.append(position + 1)
            position = protected[interval][1] + 1
            continue
        word = _match_word(text, position, words)
        if word is None:
            position += 1
            continue
        end = position + len(word)
        if word in (".", ",", "，") and position > 0 and text[position - 1].isdigit() \
                and end < len(text) and text[end].isdigit():
            position = end
            continue
        if word in ("~", "～", "-", "－", "—") and position > 0 and text[position - 1].isdigit() \
                and next((char for char in text[end:] if not char.isspace()), "").isdigit():
            position = end
            continue
        if word in (".", "…", "~", "～"):
            while text.startswith(word, end):
                end += len(word)
        # Different punctuation marks in one run express one pause. Consume
        # all adjacent configured punctuation before publishing the boundary,
        # so ``...？`` cannot leave a message beginning with ``？``.
        while True:
            following = _match_word(text, end, words)
            if following is None or not _is_punctuation_word(following):
                break
            end += len(following)
        boundaries.append(end)
        position = end
    return boundaries


COHERENCE_PROMPT = (
    "消息正文组织（只影响表达与排版，不改变角色、事实、来源和本轮任务）："
    "先把同一个意思自然说完整，紧接的回应与理由保持连贯；简短不等于只说几个字或一句就结束。"
    "对轻松、亲昵或分享式消息，可以像熟人一样自然接住情绪并多回应一点；称呼要和所在的完整句子放在一起。不要为制造聊天感，"
    "把一次接话写成一串反问、称呼、否认和重复解释。称呼和语气词随语境使用，不必每句都补。"
    "标点按语义使用，不为凑消息条数额外添加标点、换行或短句；连续标点（例如 ...？、？！）属于同一处停顿，不要在连续标点之间拆段。分段上限不是需要达到的目标。"
    "日常短消息正文内部不插入空行，每条正文首尾不填充空行；换行只用于实际内容格式或已配置的分段边界，"
    "不用空白制造停顿。代码、列表、引用和表格保持原有格式。"
)


DEFAULT_PROMPT = (
    "你可以自行决定将本轮回复作为多条消息发送：熟悉的日常聊天可按自然停顿拆成简短、各自读得通的气泡，"
    "一两句通常就够；不要把一句话、称呼与回应、因果解释或紧密相连的步骤拆散。"
    "完整回应之后的自然追问可以另发一条；模型指定的边界无需凑够规则分段的最短字数。连续标点（例如 ...？、？！）保持在同一条消息里，不要让消息以孤立标点开头。每条正文首尾不要填充空行。"
    "长文、教程、代码、引用、列表、表格、链接和带格式的内容尽量保持完整，只有清楚的主题转折才考虑分段。"
    "每个消息边界只用完整标记 {{split_marker}}，在 text 字符串内单独占一行；"
    "标记只表达消息边界，不是正文，也不能借此删改、概括或重排原文。不要加引号，不要放进代码、引用、列表或链接。"
    "JSON 内换行仍需正确转义。普通换行和空行本身不是模型指定的消息边界；仅在确有必要时使用标记。"
    "claims 中使用各段正文原句，不包含分段标记。"
)

@dataclass(frozen=True)
class SegmentationPolicy:
    enabled: bool = True
    llm_controlled: bool = False
    # Kept only so profiles written before the rules became unconditional can
    # still be parsed.  The value is intentionally ignored by ``parts``.
    rules_enabled: bool = True
    rule_mode: str = "words"
    split_words: str = json.dumps(DEFAULT_SPLIT_WORDS, ensure_ascii=False)
    match_width_variants: bool = True
    rule_regex: str = DEFAULT_RULE_REGEX
    threshold: int = 500
    min_segment_chars: int = 5
    max_segments: int = 5
    prompt: str = ""
    streaming_mode: str = "buffered"

    def __post_init__(self):
        if any(type(value) is not bool for value in (self.enabled, self.llm_controlled,
                                                     self.rules_enabled, self.match_width_variants)):
            raise ValueError("segmentation switches must be booleans")
        if self.rule_mode not in ("words", "regex", "sentences", "paragraphs"):
            raise ValueError("segmentation rule mode is invalid")
        if self.streaming_mode not in ("buffered", "incremental"):
            raise ValueError("streaming segmentation mode is invalid")
        if type(self.split_words) is not str or len(self.split_words.encode("utf-8")) > 4096:
            raise ValueError("segmentation words need a bounded JSON list")
        try:
            words = json.loads(self.split_words)
        except ValueError as error:
            raise ValueError("segmentation words need a JSON list") from error
        if (type(words) is not list or len(words) > 80
                or any(type(word) is not str or not 1 <= len(word) <= 40
                       or any(ord(char) < 32 and char != "\n" for char in word) for word in words)
                or len(words) != len(set(words))):
            raise ValueError("segmentation words need unique bounded text")
        if type(self.rule_regex) is not str or not 1 <= len(self.rule_regex) <= 512:
            raise ValueError("segmentation regex must be bounded text")
        try:
            regex.compile(self.rule_regex)
        except regex.error as error:
            raise ValueError("segmentation regex is invalid") from error
        for value, low, high in ((self.threshold, 1, 65536), (self.min_segment_chars, 1, 65536),
                                 (self.max_segments, 1, 64)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("segmentation limits must be bounded integers")
        if not isinstance(self.prompt, str) or len(self.prompt) > 4000:
            raise ValueError("segmentation prompt must be bounded text")

    @property
    def instruction(self):
        if not self.enabled:
            return ""
        if not self.llm_controlled:
            return COHERENCE_PROMPT + "本轮由程序按当前规则分段，直接生成连贯正文即可。"
        prompt = re.sub(r"\{\{\s*split_marker\s*\}\}", lambda _: LLM_SEGMENT_MARKER,
                        self.prompt or DEFAULT_PROMPT, flags=re.IGNORECASE)
        return COHERENCE_PROMPT + "\n" + prompt + f"\n分段标记为 {LLM_SEGMENT_MARKER}；本轮建议最多 {self.max_segments} 条，保持语意连贯。"

    def parts(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 65536:
            raise ValueError("segmentation needs a bounded complete reply")
        parts, _ = controlled_parts(text)
        if not parts:
            raise ValueError("reply contains only control tokens")
        if not self.enabled:
            return ("".join(parts),)
        if not self.llm_controlled:
            parts = ("".join(parts),)
        # Excess boundaries are merged, never dropped or rejected. Explicit
        # boundaries get the budget before optional rules split the longest part.
        parts = list(parts)
        if len(parts) > self.max_segments:
            parts[self.max_segments - 1:] = ["".join(parts[self.max_segments - 1:])]
        within_rule_limit = sum(map(len, parts)) <= self.threshold
        # Rule completion is part of the segmentation pipeline whenever the
        # overall segmentation switch is on.  ``rules_enabled`` remains a
        # compatibility field for old profiles, but it is no longer a user
        # choice and must never disable the deterministic fallback.
        apply_rules = within_rule_limit
        if apply_rules:
            # Repeatedly consider remaining unsplit candidates in source order,
            # preferring the longest, without splitting a rule result twice.
            while True:
                count = sum(len(p) if isinstance(p, tuple) else 1 for p in parts)
                candidates = [i for i, p in enumerate(parts) if isinstance(p, str)]
                if count >= self.max_segments or not candidates:
                    break
                index = max(candidates, key=lambda i: (len(parts[i]), -i))
                rule_parts = self._rule_parts(parts[index], self.max_segments - count + 1)
                parts[index] = tuple(self._merge_short_parts(rule_parts))
            parts = [item for p in parts for item in (p if isinstance(p, tuple) else (p,))]
        return tuple(parts)

    def _merge_short_parts(self, parts):
        if len(parts) <= 1:
            return parts

        def visible_length(value):
            return sum(not char.isspace() for char in value)

        def atomic_excerpt(value):
            stripped = value.strip()
            return (stripped.startswith("「") and stripped.endswith("」")
                    and visible_length(stripped[1:-1]) >= self.min_segment_chars)

        merged, index = [], 0
        while index < len(parts):
            current = parts[index]
            if atomic_excerpt(current):
                merged.append(current)
                index += 1
                continue
            while (index + 1 < len(parts)
                   and visible_length(current) < self.min_segment_chars
                   and not atomic_excerpt(parts[index + 1])):
                current += parts[index + 1]
                index += 1
            if (merged and not atomic_excerpt(merged[-1]) and not atomic_excerpt(current)
                    and visible_length(current) < self.min_segment_chars):
                merged[-1] += current
            else:
                merged.append(current)
            index += 1
        return merged

    def rule_boundaries(self, text):
        protected = tuple(sorted((*literal_ranges(text), *(match.span() for match in _FILE_SUFFIX.finditer(text)))))
        if self.rule_mode == "words":
            words = tuple(json.loads(self.split_words))
            if self.match_width_variants:
                words = _width_words(words)
            boundaries = _word_boundaries(text, words, protected)
        else:
            pattern = (self.rule_regex if self.rule_mode == "regex" else
                       r"(?:\r?\n[ \t]*){2,}" if self.rule_mode == "paragraphs" else
                       r"[。！？!?；;]+[”’）】]*|(?:\r?\n[ \t]*){2,}")
            try:
                boundaries = [(match.start(), match.end()) for match in regex.finditer(
                    pattern, text, timeout=0.05) if match.end() > 0]
            except TimeoutError as error:
                raise ValueError("segmentation regex exceeded its execution budget") from error
        boundaries = tuple(end for boundary in boundaries
                           if (end := boundary if isinstance(boundary, int) else boundary[1]) > 0
                           and (isinstance(boundary, int) or not any(a < end <= b for a, b in protected)))
        return _coalesce_punctuation_boundaries(text, boundaries)

    def _rule_parts(self, text, limit):
        if limit <= 1:
            return (text,)
        start, parts = 0, []
        for end in self.rule_boundaries(text):
            if end <= start:
                continue
            visible_length = sum(not char.isspace() for char in text[start:end])
            if (visible_length < self.min_segment_chars
                    or (text[end - 1] in _SOFT_COMMA_CHARS
                        and visible_length < max(_SOFT_COMMA_MIN_CHARS, self.min_segment_chars * 2))
                    or len(text[end:].strip()) < self.min_segment_chars):
                continue
            parts.append(text[start:end])
            start = end
            if len(parts) == limit - 1:
                break
        parts.append(text[start:])
        return tuple(parts)
