"""Configurable text cues for the model gateway's refusal fallback."""

from __future__ import annotations

import re


DEFAULT_REFUSAL_TERMS = (
    "很抱歉，我无法",
    "很抱歉,我无法",
    "我有我自己的底线",
    "我们可以聊聊别的",
    "我无法满足",
    "露骨性行为",
    "没办法提交这个请求",
    "这个请求没办法提交",
    "The prompt could not be submitted",
    "request could not be submitted",
)
DEFAULT_REFUSAL_TERMS_TEXT = "\n".join(DEFAULT_REFUSAL_TERMS)
MAX_REFUSAL_TERMS_CHARS = 4096
MAX_REFUSAL_TERMS_COUNT = 64
MAX_REFUSAL_TERM_CHARS = 160


def parse_refusal_terms(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or len(value) > MAX_REFUSAL_TERMS_CHARS:
        raise ValueError("refusal match terms must be bounded text")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    terms = []
    seen = set()
    for raw in re.split(r"[\n;；]+", normalized):
        term = raw.strip()
        if not term:
            continue
        if len(term) > MAX_REFUSAL_TERM_CHARS:
            raise ValueError("refusal match term is too long")
        folded = term.casefold()
        if folded not in seen:
            terms.append(term)
            seen.add(folded)
        if len(terms) > MAX_REFUSAL_TERMS_COUNT:
            raise ValueError("too many refusal match terms")
    return tuple(terms)


def canonical_refusal_terms(value: str) -> str:
    return "\n".join(parse_refusal_terms(value))


def matches_refusal_text(text: str, terms: tuple[str, ...]) -> bool:
    if not isinstance(text, str) or not text or not terms:
        return False
    folded = text.casefold()
    return any(term.casefold() in folded for term in terms)
