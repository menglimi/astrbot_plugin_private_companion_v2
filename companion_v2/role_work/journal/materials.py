"""Host-labeled writing material: an action does not authenticate its contents."""

from dataclasses import dataclass
from datetime import date
from enum import Enum

from companion_v2.execution.models import digest
from companion_v2.foundation.refs import ReferenceValidationError, SourceRef, VersionRef


MAX_JOURNAL_MATERIALS = 64


class MaterialKind(str, Enum):
    ACTION = "action"
    CREATIVE_TEXT = "creative_text"
    PUBLISHED_TEXT = "published_text"
    READING = "reading"
    CONVERSATION = "conversation"
    PLAN = "plan"
    REFLECTION = "reflection"


@dataclass(frozen=True)
class JournalMaterial:
    """Trusted producer classifies evidence; the writing model cannot promote it.

    A source may support both an ACTION (wrote/published/read) and content with
    a different kind. Related excerpts retain the same origin across dates.
    """

    material_id: str
    kind: MaterialKind
    text: str
    origin: str
    local_date: str
    source: SourceRef | None = None
    activity: VersionRef | None = None

    def __post_init__(self):
        if not isinstance(self.kind, MaterialKind):
            raise ReferenceValidationError("writing material requires its semantic kind")
        for name, maximum in (("material_id", 256), ("origin", 256), ("text", 65536)):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ReferenceValidationError("writing material text is missing or unbounded")
        if date.fromisoformat(self.local_date).isoformat() != self.local_date:
            raise ReferenceValidationError("writing material date must be explicit")
        if self.source is not None and not isinstance(self.source, SourceRef):
            raise ReferenceValidationError("writing material source must retain its reference")
        if self.activity is not None and not isinstance(self.activity, VersionRef):
            raise ReferenceValidationError("writing material activity must retain its revision")
        if self.kind is not MaterialKind.REFLECTION and self.source is None and self.activity is None:
            raise ReferenceValidationError("non-subjective material requires a source or activity")


def source_origin(source: SourceRef) -> str:
    """One work stays one origin across revisions, catalog entries and readings."""
    return "role-artifact-source-" + digest(
        [source.scope, source.owner, source.source_id, source.version.lineage_id])


def validate_materials(materials, sources, activities):
    if (not isinstance(materials, tuple) or len(materials) > MAX_JOURNAL_MATERIALS
            or any(not isinstance(item, JournalMaterial) for item in materials)
            or len({item.material_id for item in materials}) != len(materials)):
        raise ReferenceValidationError("writing materials need bounded, unique immutable identities")
    for item in materials:
        if item.source is not None and item.source not in sources:
            raise ReferenceValidationError("material source must remain a journal dependency")
        if item.activity is not None and item.activity not in activities:
            raise ReferenceValidationError("material activity must remain a journal dependency")


def material_document(item):
    # Evidence IDs group origins, never grant authority or become prose themselves.
    return {"id": item.material_id, "kind": item.kind.value, "text": item.text,
            "origin": item.origin, "date": item.local_date,
            "source": item.source.source_id if item.source else None,
            "activity": item.activity.lineage_id if item.activity else None}
