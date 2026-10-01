"""Restore journal references without changing their date, owner or source scope."""

from dataclasses import asdict
from datetime import datetime
import json

from companion_v2.foundation.refs import RoleOwnerRef, ScopeRef, SourceRef, VersionRef
from companion_v2.role_work.codec import activity_from_json
from companion_v2.execution.models import encode

from .materials import JournalMaterial, MaterialKind

from .models import (DerivativeRecord, DreamRecall, JournalContext, JournalDerivatives, JournalDraft,
                     JournalEntry, JournalHead, JournalKey, JournalKind, JournalOrigin, JournalReceipt, JournalRef, JournalState)


def key(data):
    return JournalKey(RoleOwnerRef(**data["owner"]), JournalKind(data["kind"]), data["local_date"])


def reference(data):
    return JournalRef(key(data["key"]), data["revision"])


def context(data):
    return JournalContext(key(data["key"]), ScopeRef.restore(data["scope"]), data["timezone"])


def draft_parameters(value):
    if value is None:
        return None
    data = asdict(value)
    if not value.materials:
        data.pop("materials")  # Preserve hashes of existing v17 operations.
    return data


def derivative_parameters(value):
    data = asdict(value)
    if not value.fragment_origins:
        data.pop("fragment_origins")
    return data


def source(item):
    return SourceRef(**{**item, "scope": ScopeRef.restore(item["scope"]),
        "version": VersionRef(**item["version"]), "issued_at": datetime.fromisoformat(item["issued_at"]),
        "expires_at": datetime.fromisoformat(item["expires_at"]) if item["expires_at"] else None})


def draft(data):
    sources = tuple(source(item) for item in data["sources"])
    materials = tuple(JournalMaterial(**{**item, "kind": MaterialKind(item["kind"]),
        "source": source(item["source"]) if item["source"] else None,
        "activity": VersionRef(**item["activity"]) if item["activity"] else None}) for item in data.get("materials", ()))
    return JournalDraft(**{**data, "context": context(data["context"]), "origin": JournalOrigin(data["origin"]),
        "recall": DreamRecall(data["recall"]) if data["recall"] else None, "sources": sources,
        "activities": tuple(VersionRef(**item) for item in data["activities"]),
        "journals": tuple(reference(item) for item in data["journals"]), "materials": materials})


def entry_from_row(row):
    data = json.loads(row["content_json"])
    return JournalEntry(reference(data["reference"]), draft(data["draft"]),
        tuple(activity_from_json(encode(item)) for item in data["activity_evidence"]),
        datetime.fromisoformat(data["updated_at"]))


def head_from_row(row):
    return JournalHead(context(json.loads(row["context_json"])).key, row["revision"],
                       JournalState(row["state"]), datetime.fromisoformat(row["updated_at"]))


def receipt_from_json(payload):
    data = json.loads(payload)
    head = data["head"]
    return JournalReceipt(data["operation_id"], data["action"], JournalHead(key(head["key"]), head["revision"],
        JournalState(head["state"]), datetime.fromisoformat(head["updated_at"])), data["material_revision"])


def derivatives_from_json(payload):
    data = json.loads(payload)
    material = data["material"]
    return DerivativeRecord(JournalDerivatives(**{**material, "parent": reference(material["parent"]),
        "dream_fragments": tuple(material["dream_fragments"]),
        "fragment_origins": tuple(tuple(ids) for ids in material.get("fragment_origins", ()))}),
        data["revision"], datetime.fromisoformat(data["updated_at"]))
