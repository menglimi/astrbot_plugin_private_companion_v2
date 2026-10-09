"""Internal transport evidence; never infer submission from a selection plan."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class ReferenceReceipt:
    status: str = "not_submitted"
    uploaded: list[dict[str, str]] = field(default_factory=list)
    submitted: list[dict[str, str]] = field(default_factory=list)
    task_id: str = ""
    stage: str = "reference_preparation"
    generation_completed: bool = False

    def upload(self, path: str, slot: str) -> None:
        self.uploaded.append({"path": str(path), "slot": slot})

    def attempting(self) -> None:
        # A lost response cannot establish whether the provider accepted it.
        self.status = "unknown"
        self.stage = "submission"

    def accept(self, entries: list[dict[str, str]], *, task_id: str = "") -> None:
        self.submitted = [dict(entry) for entry in entries]
        self.status = "submitted" if entries else "not_submitted"
        self.task_id = task_id
        self.stage = "result"

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "uploaded": [dict(entry) for entry in self.uploaded],
            "submitted": [dict(entry) for entry in self.submitted],
            "task_id": self.task_id,
            "stage": self.stage,
            "generation_completed": self.generation_completed,
        }


def reference_result_fields(receipt: Any, references: Any) -> dict[str, Any]:
    """Translate transport paths to this attempt's IDs, rejecting foreign evidence."""
    unknown = {
        "reference_submission_status": "unknown",
        "uploaded_reference_ids": (),
        "submitted_reference_ids": (),
        "reference_submission_slots": (),
    }
    if not isinstance(receipt, Mapping) or not isinstance(receipt.get("status"), str) or receipt.get("status") not in {
        "unknown", "not_submitted", "submitted",
    }:
        return unknown
    by_path: dict[str, list[str]] = {}
    for reference in references:
        key = os.path.normcase(os.path.abspath(reference.path))
        by_path.setdefault(key, []).append(reference.reference_id)
    resolved: dict[str, tuple[str, ...]] = {}
    slots: list[dict[str, str]] = []
    for kind in ("uploaded", "submitted"):
        entries = receipt.get(kind)
        if not isinstance(entries, (list, tuple)):
            return unknown
        ids = []
        for entry in entries:
            if (not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str)
                    or not entry["path"] or not isinstance(entry.get("slot"), str)):
                return unknown
            matches = by_path.get(os.path.normcase(os.path.abspath(entry["path"])))
            if not matches:
                return unknown
            ids.extend(matches)
            if kind == "submitted":
                slots.extend({"reference_id": value, "slot": entry["slot"]} for value in matches)
        resolved[kind] = tuple(dict.fromkeys(ids))
    if bool(resolved["submitted"]) != (receipt["status"] == "submitted"):
        return unknown
    return {
        "reference_submission_status": receipt["status"],
        "uploaded_reference_ids": resolved["uploaded"],
        "submitted_reference_ids": resolved["submitted"],
        "reference_submission_slots": tuple(slots),
    }
