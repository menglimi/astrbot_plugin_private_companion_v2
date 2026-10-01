"""Lossless decoding of memory records; no inferred identity or source versions."""

from companion_v2.foundation.refs import ScopeRef, SourceRef, VersionRef
from .models import AtomRef, Evidence, Proposal, timestamp


def source(value):
    return SourceRef(value["source_id"], value["owner"], ScopeRef.restore(value["scope"]),
        VersionRef(**value["version"]), timestamp(value["issued_at"]), timestamp(value["expires_at"]))


def evidence(value):
    return Evidence(**{**value, "source": source(value["source"])})


def proposal(value):
    return Proposal(**{**value, "evidence": tuple(evidence(e) for e in value.get("evidence", ())),
        "target": AtomRef(**value["target"]) if value.get("target") else None,
        "dependencies": tuple(AtomRef(**r) for r in value.get("dependencies", ()))})
