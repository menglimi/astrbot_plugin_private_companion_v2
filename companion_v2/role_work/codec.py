"""Restore role-owned records without resolving paths or changing source scope."""

from datetime import datetime
import json

from companion_v2.foundation.refs import AssetRef, RoleOwnerRef, ScopeRef, SourceRef, VersionRef

from .models import (RoleActivity, RoleActivityState, RoleArtifact, RoleArtifactJournalMeaning,
                     RoleArtifactKind, RoleReadingReceipt, RoleSleepReceipt)
from .work_models import RoleWorkSpec


def source_from_document(source):
    return SourceRef(**{**source, "scope": ScopeRef.restore(source["scope"]),
        "version": VersionRef(**source["version"]), "issued_at": datetime.fromisoformat(source["issued_at"]),
        "expires_at": datetime.fromisoformat(source["expires_at"]) if source["expires_at"] else None})


def activity_from_json(payload: str) -> RoleActivity:
    data = json.loads(payload)
    work = data.get("work")
    if work is not None:
        work = RoleWorkSpec(**{**work, "source": source_from_document(work["source"]) if work.get("source") else None,
            "due_at": datetime.fromisoformat(work["due_at"]) if work.get("due_at") else None})
    reading = data.get("reading")
    if reading is not None:
        reading = RoleReadingReceipt(**{**reading, "source": source_from_document(reading["source"]),
            "completed_at": datetime.fromisoformat(reading["completed_at"])})
    sleep = data.get("sleep")
    if sleep is not None:
        sleep = RoleSleepReceipt(**{**sleep,
            "wake_until": datetime.fromisoformat(sleep["wake_until"]) if sleep.get("wake_until") else None})
    return RoleActivity(**{**data, "scope": ScopeRef.restore(data["scope"]),
        "state": RoleActivityState(data["state"]), "started_at": datetime.fromisoformat(data["started_at"]),
        "updated_at": datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        "reading": reading, "work": work, "sleep": sleep})


def artifact_from_json(payload: str) -> RoleArtifact:
    data = json.loads(payload)
    source = source_from_document(data["source"])
    asset = data["asset"]
    if asset is not None:
        asset = AssetRef(**{**asset, "scope": ScopeRef.restore(asset["scope"]), "version": VersionRef(**asset["version"])})
    return RoleArtifact(**{**data, "kind": RoleArtifactKind(data["kind"]),
        "journal_meaning": RoleArtifactJournalMeaning(data.get("journal_meaning", "unclassified")),
        "source": source, "asset": asset,
        "owner": RoleOwnerRef(**data["owner"]), "created_at": datetime.fromisoformat(data["created_at"])})
