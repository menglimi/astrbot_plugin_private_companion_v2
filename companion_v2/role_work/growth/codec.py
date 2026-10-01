"""Stable JSON codec for role growth revisions."""

from __future__ import annotations

from datetime import datetime
import json

from companion_v2.execution.models import encode
from companion_v2.foundation.refs import (
    RoleOwnerRef,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    VersionRef,
)

from .models import GrowthKind, GrowthState, RoleGrowthRecord


def record_json(record: RoleGrowthRecord) -> str:
    return encode(record)


def _subject(value: dict | None) -> SubjectRef | None:
    if value is None:
        return None
    return SubjectRef(**{**value, "kind": SubjectKind(value["kind"])})


def record_from_json(value: str) -> RoleGrowthRecord:
    data = json.loads(value)
    sources = tuple(
        SourceRef(
            source_id=item["source_id"],
            owner=item["owner"],
            scope=ScopeRef.restore(item["scope"]),
            version=VersionRef(**item["version"]),
            issued_at=datetime.fromisoformat(item["issued_at"]),
            expires_at=datetime.fromisoformat(item["expires_at"]) if item["expires_at"] else None,
        )
        for item in data["sources"]
    )
    return RoleGrowthRecord(
        growth_id=data["growth_id"],
        owner=RoleOwnerRef(**data["owner"]),
        scope=ScopeRef.restore(data["scope"]),
        kind=GrowthKind(data["kind"]),
        title=data["title"],
        description=data["description"],
        progress_note=data["progress_note"],
        sources=sources,
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
        revision=data["revision"],
        state=GrowthState(data["state"]),
        proposed_by=_subject(data.get("proposed_by")),
        confirmed_by=_subject(data.get("confirmed_by")),
        changed_by=_subject(data.get("changed_by")),
    )
