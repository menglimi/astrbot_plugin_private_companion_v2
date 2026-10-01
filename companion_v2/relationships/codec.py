"""Stable JSON codec for relationship memory snapshots."""

from __future__ import annotations

from datetime import datetime
import json

from companion_v2.foundation.refs import (
    RoleOwnerRef,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    VersionRef,
)
from companion_v2.execution.models import encode

from .models import EmotionSubject, RelationshipMemory, RelationshipMemoryKind, RelationshipMemoryState


def memory_json(memory: RelationshipMemory) -> str:
    return encode(memory)


def _subject_from_json(value: dict | None) -> SubjectRef | None:
    if value is None:
        return None
    return SubjectRef(**{**value, "kind": SubjectKind(value["kind"])})


def memory_from_json(value: str) -> RelationshipMemory:
    data = json.loads(value)
    owner = RoleOwnerRef(**data["owner"])
    subject_data = dict(data["subject"])
    subject_data["kind"] = SubjectKind(subject_data["kind"])
    subject = SubjectRef(**subject_data)
    sources = tuple(
        SourceRef(
            source_id=source["source_id"],
            owner=source["owner"],
            scope=ScopeRef.restore(source["scope"]),
            version=VersionRef(**source["version"]),
            issued_at=datetime.fromisoformat(source["issued_at"]),
            expires_at=datetime.fromisoformat(source["expires_at"]) if source["expires_at"] else None,
        )
        for source in data["sources"]
    )
    return RelationshipMemory(
        memory_id=data["memory_id"],
        owner=owner,
        subject=subject,
        scope=ScopeRef.restore(data["scope"]),
        kind=RelationshipMemoryKind(data["kind"]),
        interpretation=data["interpretation"],
        sources=sources,
        created_at=datetime.fromisoformat(data["created_at"]),
        observed_at=datetime.fromisoformat(data["observed_at"]),
        revision=data["revision"],
        state=RelationshipMemoryState(data["state"]),
        emotion_subject=EmotionSubject(data["emotion_subject"]) if data["emotion_subject"] else None,
        updated_at=datetime.fromisoformat(data["updated_at"]),
        reviewed_by=_subject_from_json(data.get("reviewed_by")),
        adopted_by=_subject_from_json(data.get("adopted_by")),
        retracted_by=_subject_from_json(data.get("retracted_by")),
        revised_by=_subject_from_json(data.get("revised_by")),
    )
