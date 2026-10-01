"""Persistent, V2-local progress for the one-time first-run guide."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4


SCHEMA_VERSION = 2
SETUP_STEPS = ("model", "knowledge", "relationships")
MODES = {"accounts": ("single", "multiple"), "personas": ("single", "multiple")}


def empty_state() -> dict:
    return {"schema_version": SCHEMA_VERSION, "mode": None, "completed": [],
            "skipped": [], "proactive_test": None, "ready": False}


class SetupStateStore:
    def __init__(self, data_root):
        self.root = Path(data_root).resolve() / "setup"
        self.path = self.root / "progress.json"

    def read(self) -> dict:
        if not self.path.exists():
            return empty_state()
        raw = self.path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("setup progress must be UTF-8 without BOM")
        document = json.loads(raw.decode("utf-8"))
        if type(document) is not dict:
            raise ValueError("setup progress has an unsupported shape")
        if document.get("schema_version") == 1:
            old_fields = {"schema_version", "mode", "completed", "proactive_test", "ready"}
            if set(document) != old_fields or type(document.get("completed")) is not list:
                raise ValueError("setup progress has an unsupported shape")
            old_test = document["proactive_test"]
            if old_test is not None:
                if type(old_test) is not dict:
                    raise ValueError("setup test receipt is invalid")
                tested_at = old_test.get("tested_at")
                if old_test.get("state") != "delivered" or type(tested_at) is not str:
                    raise ValueError("setup test receipt is invalid")
                old_test = {"state": "delivered", "attempt_id": "previous-setup",
                            "started_at": tested_at, "finished_at": tested_at}
            document = {**empty_state(), "mode": document["mode"],
                        "completed": document["completed"],
                        "proactive_test": old_test,
                        "ready": document["ready"]}
        if (document.get("schema_version") != SCHEMA_VERSION
                or set(document) != {"schema_version", "mode", "completed", "skipped", "proactive_test", "ready"}
                or type(document.get("completed")) is not list
                or type(document.get("skipped")) is not list
                or any(item not in SETUP_STEPS for item in document["completed"] + document["skipped"])
                or len(set(document["completed"])) != len(document["completed"])
                or len(set(document["skipped"])) != len(document["skipped"])
                or set(document["completed"]) & set(document["skipped"])
                or type(document.get("ready")) is not bool):
            raise ValueError("setup progress has an unsupported shape")
        mode = document["mode"]
        if mode is not None and (type(mode) is not dict or set(mode) != set(MODES)
                or any(mode[key] not in allowed for key, allowed in MODES.items())):
            raise ValueError("setup mode is invalid")
        test = document["proactive_test"]
        if test is not None:
            if (type(test) is not dict or test.get("state") not in ("started", "unknown", "delivered")
                    or type(test.get("attempt_id")) is not str
                    or type(test.get("started_at")) is not str):
                raise ValueError("setup test receipt is invalid")
            if test["state"] in ("unknown", "delivered") and type(test.get("finished_at")) is not str:
                raise ValueError("setup test receipt is invalid")
        if document["ready"] != bool(test and test.get("state") == "delivered"):
            raise ValueError("setup completion does not match the proactive test receipt")
        return document

    def write(self, document: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name("." + self.path.name + "." + uuid4().hex + ".tmp")
        payload = json.dumps(document, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, indent=2) + "\n"
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def select_mode(self, *, accounts: str, personas: str) -> dict:
        if accounts not in MODES["accounts"] or personas not in MODES["personas"]:
            raise ValueError("setup mode is invalid")
        state = self.read()
        mode = {"accounts": accounts, "personas": personas}
        if state["mode"] != mode:
            state = {**empty_state(), "mode": mode}
            self.write(state)
        return state

    def complete(self, step: str, *, skipped: bool = False) -> dict:
        if step not in SETUP_STEPS:
            raise ValueError("unknown setup step")
        state = self.read()
        if state["mode"] is None:
            raise ValueError("select the setup mode first")
        destination = "skipped" if skipped else "completed"
        other = "completed" if skipped else "skipped"
        if step not in state[destination]:
            state[destination].append(step)
        if step in state[other]:
            state[other].remove(step)
        self.write(state)
        return state

    def begin_proactive_test(self, *, attempt_id: str, started_at: str) -> dict:
        state = self.read()
        if state["ready"]:
            return state
        if state["proactive_test"] is not None:
            raise ValueError("the proactive test has already started and cannot be replayed")
        if state["mode"] is None or any(step not in state["completed"] + state["skipped"]
                                         for step in SETUP_STEPS):
            raise ValueError("complete the guided setup steps first")
        state["proactive_test"] = {"state": "started", "attempt_id": attempt_id,
                                    "started_at": started_at}
        self.write(state)
        return state

    def finish_proactive_test(self, *, delivered: bool, finished_at: str) -> dict:
        state = self.read()
        receipt = state["proactive_test"]
        if not receipt or receipt["state"] != "started":
            raise ValueError("there is no in-flight proactive test")
        receipt["state"] = "delivered" if delivered else "unknown"
        receipt["finished_at"] = finished_at
        state["ready"] = delivered
        self.write(state)
        return state
