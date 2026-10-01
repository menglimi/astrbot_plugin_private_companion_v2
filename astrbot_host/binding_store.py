"""Where a first-run binding is kept until the profile is pinned.

Binding has to be written before the profile exists: the operator sends the command
precisely because nothing is pinned yet, and the pinned document cannot be created
until the target it would pin is known. So the choice is parked here, in the
profile directory, next to the pin it will become.

Two rules keep this from becoming a second source of truth:

* **It is consulted only while nothing is pinned.** Once ``staging-config.json``
  exists, that document owns the identity and this file is ignored. A stale binding
  file therefore cannot quietly redirect a working installation.
* **It is written atomically, like the pin.** Same temporary-then-rename dance as
  ``_write_intent``: a half-written binding file would be worse than none, because
  the next start would read a target that was never confirmed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .identity_derivation import derived_identity, normalize_persona_id


BINDING_FILENAME = "binding.json"
BINDING_SCHEMA = 2

_FIELDS = ("platform_id", "account_id", "participant_id", "persona_id")


@dataclass(frozen=True)
class PendingBinding:
    """A candidate target awaiting an administrator's confirmation."""

    platform_id: str
    account_id: str
    participant_id: str
    persona_id: str = ""
    confirmed: bool = False

    def identity(self) -> dict[str, str]:
        """The pinned identity block this binding resolves to."""
        return derived_identity(platform_id=self.platform_id, account_id=self.account_id,
                                participant_id=self.participant_id, persona_id=self.persona_id)

    def document(self) -> dict:
        return {"schema_version": BINDING_SCHEMA,
                **{name: getattr(self, name) for name in _FIELDS},
                "confirmed": self.confirmed}

    @classmethod
    def parse(cls, text: str) -> "PendingBinding":
        """Read a stored binding.

        Raises ``ValueError`` on anything unexpected rather than repairing it: a
        binding file that cannot be read is a reason to rebind, not a reason to
        guess which conversation the role should talk to.
        """
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("binding must be an object")
        version = data.get("schema_version")
        if version not in (1, BINDING_SCHEMA):
            raise ValueError("unsupported binding version")
        if set(data) - set(_FIELDS) - {"schema_version", "confirmed"}:
            raise ValueError("binding has unknown fields")
        for name in ("platform_id", "account_id", "participant_id"):
            if type(data.get(name)) is not str or not data[name]:
                raise ValueError("binding is missing " + name)
        confirmed = data.get("confirmed", False)
        if type(confirmed) is not bool:
            raise ValueError("binding confirmation must be boolean")
        # Schema 1 bindings were never confirmed by an authenticated Dashboard
        # administrator; keep them visible as candidates until reviewed.
        return cls(platform_id=data["platform_id"], account_id=data["account_id"],
                   participant_id=data["participant_id"],
                   persona_id=normalize_persona_id(data.get("persona_id", "")),
                   confirmed=confirmed if version == BINDING_SCHEMA else False)


def binding_path(profile_root: Path) -> Path:
    return Path(profile_root) / BINDING_FILENAME


def read_binding(profile_root: Path) -> PendingBinding | None:
    """The parked binding, or None when there is not one.

    An unreadable file is treated as absent rather than fatal: the operator's next
    move is to bind again either way, and refusing to load the plugin over a
    truncated first-run file would be a worse failure than asking them to redo one
    command.
    """
    path = binding_path(profile_root)
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            return None
        return PendingBinding.parse(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None


def write_binding(profile_root: Path, binding: PendingBinding) -> None:
    """Store the binding atomically, so a crash cannot leave a partial target."""
    path = binding_path(profile_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid4().hex + ".tmp")
    payload = json.dumps(binding.document(), ensure_ascii=False, allow_nan=False,
                         sort_keys=True, indent=2) + "\n"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def clear_binding(profile_root: Path) -> bool:
    """Forget a parked binding. Returns whether one was there."""
    path = binding_path(profile_root)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
