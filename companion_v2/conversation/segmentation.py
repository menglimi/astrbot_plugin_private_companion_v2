"""Deterministic reply segmentation shared by streamed and complete replies."""

from dataclasses import dataclass
import hashlib
import json
import math
import re

import regex

from .segment_control import LLM_SEGMENT_MARKER, controlled_parts, protected_ranges
from .text_processing import literal_ranges


DEFAULT_SPLIT_WORDS = ("。", "？", "！", "~", "…", "“", "\n")
DEFAULT_RULE_REGEX = r".*?[。？！~…\n]+|.+$"
PART_GAP_MODES = frozenset(("fixed", "random", "log"))


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
        base = settings.get("part_gap_log_base", 1.8)
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
        base = settings.get("part_gap_log_base", 1.8)
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
        word = next((word for word in words if text.startswith(word, position)), None)
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
        boundaries.append(end)
        position = end
    return boundaries


DEFAULT_PROMPT = (
    "你可以自行决定将本轮回复作为多条消息发送。日常聊天可用短句分段；长文、教程、代码尽量少拆。"
    "每个消息边界只用完整标记 {{split_marker}}，在 text 字符串内单独占一行；"
    "不要加引号，不要放进代码、引用、列表或链接。JSON 内换行仍需正确转义。"
    "普通换行和空行本身不是模型指定的消息边界。仅在确有必要时使用。"
    "claims 中使用各段正文原句，不包含分段标记。"
)


@dataclass(frozen=True)
class SegmentationPolicy:
    enabled: bool = False
    llm_controlled: bool = True
    rules_enabled: bool = False
    rule_mode: str = "words"
    split_words: str = json.dumps(DEFAULT_SPLIT_WORDS, ensure_ascii=False)
    match_width_variants: bool = True
    rule_regex: str = DEFAULT_RULE_REGEX
    threshold: int = 120
    min_segment_chars: int = 12
    max_segments: int = 4
    prompt: str = ""

    def __post_init__(self):
        if any(type(value) is not bool for value in (self.enabled, self.llm_controlled,
                                                     self.rules_enabled, self.match_width_variants)):
            raise ValueError("segmentation switches must be booleans")
        if self.rule_mode not in ("words", "regex", "sentences", "paragraphs"):
            raise ValueError("segmentation rule mode is invalid")
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
        if not self.enabled or not self.llm_controlled:
            return ""
        prompt = re.sub(r"\{\{\s*split_marker\s*\}\}", lambda _: LLM_SEGMENT_MARKER,
                        self.prompt or DEFAULT_PROMPT, flags=re.IGNORECASE)
        return prompt + f"\n分段标记为 {LLM_SEGMENT_MARKER}；本轮建议最多 {self.max_segments} 条，保持语意连贯。"

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
        if self.rules_enabled:
            # Repeatedly consider remaining unsplit candidates in source order,
            # preferring the longest, without splitting a rule result twice.
            while True:
                count = sum(len(p) if isinstance(p, tuple) else 1 for p in parts)
                candidates = [i for i, p in enumerate(parts) if isinstance(p, str)]
                if count >= self.max_segments or not candidates:
                    break
                index = max(candidates, key=lambda i: (len(parts[i]), -i))
                parts[index] = self._rule_parts(parts[index], self.max_segments - count + 1)
            parts = [item for p in parts for item in (p if isinstance(p, tuple) else (p,))]
        return tuple(parts)

    def _rule_parts(self, text, limit):
        if len(text) < self.threshold or limit <= 1:
            return (text,)
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
                    pattern, text, timeout=0.05) if match.start() < match.end()]
            except TimeoutError as error:
                raise ValueError("segmentation regex exceeded its execution budget") from error
        start, parts = 0, []
        for boundary in boundaries:
            end = boundary if isinstance(boundary, int) else boundary[1]
            if end <= start:
                continue
            if not isinstance(boundary, int) and any(a < end <= b for a, b in protected):
                continue
            if (len(text[start:end].strip()) < self.min_segment_chars
                    or len(text[end:].strip()) < self.min_segment_chars):
                continue
            parts.append(text[start:end])
            start = end
            if len(parts) == limit - 1:
                break
        parts.append(text[start:])
        return tuple(parts)
