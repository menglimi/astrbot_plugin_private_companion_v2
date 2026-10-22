"""Where a target's data actually lives, when the selected profile is not it.

A store is per-profile (``profiles/<profile_id>/runtime``), so pointing
``staging.profile_id`` at a new name does not move anything: the role opens an empty
store and reads as if it had forgotten everything, while the old one sits untouched on
disk. Nothing is lost, but nothing says so either, and "it forgot me" is exactly what
this project must never look like.

This module answers one question for a human: *the selected profile has no data for this
target — does another profile have it?* It only reports when a profile matches the same
target **and** that profile's store actually holds rows, so an ordinary first run, a
fresh preview profile, or an unrelated target never produces a warning.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from companion_v2.storage.sqlite_path import readonly_uri

# A store file must be at least this large to count as "holds data". An empty
# provisioned store is a few dozen KB of schema, so size alone is a poor signal; the
# caller's row check does the real work and this only screens out tiny leftovers.
MIN_STORE_BYTES = 4096


def _selected_target(document: dict) -> tuple | None:
    """The (platform, account, participant) a pinned document was built for."""
    scope = document.get("scope")
    subject = document.get("subject")
    if not isinstance(scope, dict):
        return None
    participant = subject.get("subject_id") if isinstance(subject, dict) else None
    if not isinstance(participant, str) or not participant:
        # Older documents carry the human only in the scope.
        participant = scope.get("native_scope_id")
    platform = scope.get("platform")
    account = scope.get("account_id")
    if not all(isinstance(value, str) and value for value in (platform, account, participant)):
        return None
    return platform, account, participant


def _store_holds_data(runtime: Path) -> bool:
    """Whether this store has recorded anything, not merely whether it exists.

    Every provisioned store carries the full schema (100+ empty tables), so its file is
    hundreds of KB before a single conversation happens. Size therefore proves nothing —
    an early version of this check compared the file against a byte threshold and
    reported "holds data" for every profile on the machine, which silently disabled the
    whole diagnostic. Only a row count can answer this.
    """
    store = runtime / "companion-v2.sqlite3"
    if not store.is_file() or store.stat().st_size < MIN_STORE_BYTES:
        return False
    try:
        connection = sqlite3.connect(readonly_uri(store), uri=True, timeout=2.0)
    except sqlite3.Error:
        return False
    try:
        for table, column in (("conversation_inputs", "batch_id"), ("memory_notes", "owner_key"),
                              ("execution_tasks", "task_id")):
            try:
                row = connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()
            except sqlite3.Error:
                continue
            if row is not None:
                return True
        return False
    finally:
        connection.close()


def profile_residency(data_root: Path, *, profile_id: str, target: tuple | None) -> dict | None:
    """Which other profile holds data for ``target``, if the selected one does not.

    Returns ``None`` when the selected profile already has data, when no other profile
    matches the target, or when the target is unknown. Never raises: a diagnostic that
    can break the page it is meant to explain is worse than no diagnostic.
    """
    if not target or not profile_id:
        return None
    profiles = Path(data_root) / "profiles"
    if not profiles.is_dir():
        return None
    try:
        selected_runtime = profiles / profile_id / "runtime"
        if _store_holds_data(selected_runtime):
            return None
        holders = []
        for directory in sorted(profiles.iterdir()):
            if not directory.is_dir() or directory.name == profile_id:
                continue
            document_path = directory / "staging-config.json"
            if not document_path.is_file() or not _store_holds_data(directory / "runtime"):
                continue
            try:
                document = json.loads(document_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(document, dict) and _selected_target(document) == target:
                holders.append(directory.name)
    except OSError:
        return None
    if not holders:
        return None
    return {"selected": profile_id, "holders": holders}
