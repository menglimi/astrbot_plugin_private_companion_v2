"""Shared installation-core check for chat commands that change shared state."""

from __future__ import annotations

from companion_v2.identity_policy.models import AuthorizationTier


def is_core_subject(runtime, subject):
    if runtime is None or subject is None:
        return False
    row = runtime.read_one(
        "SELECT tier FROM subject_access_tiers WHERE subject_kind = ? AND subject_id = ?",
        (subject.kind.value, subject.subject_id))
    return row is not None and row["tier"] == AuthorizationTier.CORE.value
