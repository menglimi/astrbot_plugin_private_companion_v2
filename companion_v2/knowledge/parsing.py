"""Format parsing only; selection, authorization, retrieval and prompt injection belong elsewhere."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Generic, Mapping, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class ParseIssue:
    index: int
    code: str


@dataclass(frozen=True)
class ParseBatch(Generic[T]):
    items: tuple[T, ...]
    issues: tuple[ParseIssue, ...]


@dataclass(frozen=True)
class WorldbookEntry:
    entry_id: str | None
    template: str
    name: str
    gender: str
    enabled: bool
    priority: int
    scope: tuple[str, ...]
    keywords: tuple[str, ...]
    aliases: tuple[str, ...]
    content: str


@dataclass(frozen=True)
class KnowledgeChunk:
    text: str
    knowledge_base_id: str
    document_id: str
    document_name: str
    chunk_index: int


def _strings(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(field)
    if any(type(item) is not str for item in value):
        raise ValueError(field)
    return tuple(item.strip() for item in value if item.strip())


def _worldbook_entry(raw: object) -> WorldbookEntry:
    if not isinstance(raw, Mapping):
        raise ValueError("entry")
    name = raw.get("name", "")
    content = raw.get("content", "")
    template = raw.get("__template_key", raw.get("template", ""))
    gender = raw.get("gender", raw.get("性别", ""))
    identifier = raw.get("id", raw.get("entry_id"))
    enabled = raw.get("enabled", True)
    priority = raw.get("priority", 100)
    if any(type(value) is not str for value in (name, content, template, gender)):
        raise ValueError("text_field")
    if identifier is not None and (type(identifier) is not str or not identifier.strip()):
        raise ValueError("entry_id")
    if type(enabled) is not bool:
        raise ValueError("enabled")
    if type(priority) is not int:
        raise ValueError("priority")
    if not name.strip() and not content.strip():
        raise ValueError("empty_entry")
    return WorldbookEntry(
        entry_id=identifier.strip() if identifier else None,
        template=template.strip().lower(),
        name=name.strip(),
        gender=gender.strip(),
        enabled=enabled,
        priority=priority,
        scope=_strings(raw.get("scope"), "scope"),
        keywords=_strings(raw.get("keywords"), "keywords"),
        aliases=_strings(raw.get("aliases"), "aliases"),
        content=content.strip(),
    )


def parse_worldbook(payload: object) -> ParseBatch[WorldbookEntry]:
    """Parse an AstrBot worldbook export or a raw entry list without activating it."""
    rows = payload.get("entry_storage") if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError("worldbook must contain an entry_storage list")
    items, issues = [], []
    for index, row in enumerate(rows):
        try:
            items.append(_worldbook_entry(row))
        except ValueError as error:
            issues.append(ParseIssue(index, str(error)))
    return ParseBatch(tuple(items), tuple(issues))


def _metadata(value: object) -> Mapping[str, object]:
    if value is None or value == "":
        return {}
    if isinstance(value, Mapping):
        return value
    if type(value) is str:
        decoded = json.loads(value)
        if isinstance(decoded, Mapping):
            return decoded
    raise ValueError("metadata")


def _identifier(value: object, field: str) -> str:
    if value is None:
        return ""
    if type(value) is not str:
        raise ValueError(field)
    return value.strip()


def parse_knowledge_rows(
    rows: object,
    *,
    knowledge_base_id: str = "",
) -> ParseBatch[KnowledgeChunk]:
    """Normalize AstrBot knowledge document rows; does not filter or rank chunks."""
    if not isinstance(rows, (list, tuple)):
        raise ValueError("knowledge rows must be a list")
    if type(knowledge_base_id) is not str:
        raise ValueError("knowledge_base_id")
    items, issues = [], []
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, Mapping):
                raise ValueError("row")
            text = row.get("text")
            if type(text) is not str or not text.strip():
                raise ValueError("text")
            metadata = _metadata(row.get("metadata"))
            document_id = _identifier(metadata.get("kb_doc_id", row.get("document_id")), "document_id")
            document_name = _identifier(metadata.get("doc_name", row.get("document_name")), "document_name")
            raw_index = metadata.get("chunk_index", row.get("chunk_index", 0))
            if type(raw_index) is str and raw_index.isdecimal():
                raw_index = int(raw_index)
            if type(raw_index) is not int or raw_index < 0:
                raise ValueError("chunk_index")
            items.append(KnowledgeChunk(text.strip(), knowledge_base_id.strip(), document_id,
                                        document_name, raw_index))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            issues.append(ParseIssue(index, str(error) or "invalid_row"))
    return ParseBatch(tuple(items), tuple(issues))
