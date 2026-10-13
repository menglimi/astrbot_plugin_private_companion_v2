"""Optional, owner-side Role provenance port for actually issued RV-1 originals.

No device reads or bodies are stored here. The host must refresh the invocation
on its event-loop thread before a storage operation. Worker guards then fence
the same gateway/access state without calling event-loop-only identity methods.
This port is explicitly assembled; the legacy consumer ledger is unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

from .mobile_snapshot_owner import OwnerFailure, _authority, _disclosure, _encode


def _hash(value):
    return hashlib.sha256(_encode(value)).hexdigest()


class RoleSnapshotSources:
    owner_ref = "owner:reality-mobile"

    def __init__(self, native, host_api):
        if native._host is not host_api or not getattr(native.gateway, "data_dir", None):
            raise OwnerFailure("unavailable", "provider_unavailable")
        self.native, self.host_api = native, host_api
        self.path = Path(native.gateway.data_dir) / "role_snapshot_sources.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._issued = {}
        with self._database() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS role_snapshot_inputs (
                snapshot_ref TEXT PRIMARY KEY, dependency_json TEXT NOT NULL,
                disclosure_sha256 TEXT NOT NULL, generation TEXT NOT NULL,
                source_ref TEXT NOT NULL, epoch INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS role_snapshot_registrations (
                registration_id TEXT PRIMARY KEY, registration_sha256 TEXT NOT NULL,
                snapshot_ref TEXT NOT NULL, target_json TEXT NOT NULL,
                dependency_sha256 TEXT NOT NULL, governance_revision INTEGER NOT NULL)""")

    @contextmanager
    def _database(self):
        db = sqlite3.connect(self.path, timeout=1)
        try:
            with db:
                yield db
        finally:
            db.close()

    def prepare(self, invocation):
        """Main-thread authentication; returns an envelope, never a credential."""
        if threading.get_ident() != self.native._access._thread_id:
            raise OwnerFailure("rejected", "access_denied")
        return self.native.envelope(invocation)

    @contextmanager
    def guard(self, invocation):
        native, access = self.native, self.native._access
        # Native code sometimes takes access -> gateway and sometimes the
        # reverse. Never wait for the second lock while holding the first.
        if not native.gateway._mobile_state_lock.acquire(blocking=False):
            raise OwnerFailure("unavailable", "provider_unavailable")
        acquired = False
        try:
            acquired = access._lock.acquire(blocking=False)
            if not acquired:
                raise OwnerFailure("unavailable", "provider_unavailable")
            claims = self._claims_locked(invocation)
            watermark = self._watermark(claims)
            yield claims
            if self._claims_locked(invocation) != claims or self._watermark(claims) != watermark:
                raise OwnerFailure("unavailable", "provider_unavailable")
        finally:
            if acquired:
                access._lock.release()
            native.gateway._mobile_state_lock.release()

    def _claims_locked(self, invocation):
        native, access = self.native, self.native._access
        grant = access._grants.get(invocation)
        if (grant is None or access._pending_invalidation
                or time.monotonic() >= grant.monotonic_expiry
                or native._host is not self.host_api
                or native.gateway.v2_host_api() is not self.host_api
                or not callable(native.provider_current) or not native.provider_current()):
            raise OwnerFailure("rejected", "access_denied")
        claims = json.loads(grant.claims)
        if (claims["authorization_ref"] != access.generation
                or claims["authorization_revision"] != access.revision
                or datetime.now(timezone.utc) >= datetime.fromisoformat(claims["deadline_at"])):
            raise OwnerFailure("rejected", "access_denied")
        user = claims["user_id"]
        state = native._users.get(user)
        if (state is None or user != native.gateway._mobile_allowed_user_id()
                or state.policy != native._policy()
                or state.authority_state != _encode([claims["subject_ref"], access.generation, access.revision])):
            raise OwnerFailure("unavailable", "provider_unavailable")
        return claims

    def _watermark(self, claims):
        state = self.native._users[claims["user_id"]]
        return _hash([self.native.generation, claims["authorization_ref"], claims["authorization_revision"],
                      state.subject_ref, state.authorization_revision, state.binding_revision,
                      state.epochs, state.policy])

    def watermark(self, invocation):
        return self._watermark(self._claims_locked(invocation))

    def capture(self, invocation, *, source_ref, snapshot_ref):
        """Issue exact metadata only after a real adapter read disclosed it."""
        envelope = self.prepare(invocation)
        with self.guard(invocation):
            saved = self.native._notices.get(snapshot_ref)
            notice = saved[0] if saved else None
            if (not notice or notice["source_ref"] != source_ref
                    or notice["authority"] != _authority(envelope)
                    or notice["disclosure"] != _disclosure(envelope)
                    or not notice["reference_supported"]
                    or notice["expires_at"] <= datetime.now(timezone.utc)):
                raise OwnerFailure("rejected", "access_denied")
            claims = self._claims_locked(invocation)
            state = self.native._users[claims["user_id"]]
            kind = next((kind for kind in state.epochs
                         if self.native.source_ref(claims["user_id"], kind) == source_ref), None)
            if kind is None:
                raise OwnerFailure("rejected", "access_denied")
            if (notice.get("role_generation") != self.native.generation
                    or notice.get("role_epoch") != str(state.epochs[kind])):
                raise OwnerFailure("invalidated", "snapshot_invalidated")
            context = envelope["context"]
            dependency = {
                "input_id": "input:" + _hash([self.owner_ref, snapshot_ref]),
                "owner_ref": self.owner_ref,
                "reference": {"kind": "reality.snapshot", "ref": snapshot_ref, "revision": None},
                "version_kind": "immutable_ref", "access_ref": context["authorization_ref"],
                "access_revision": context["authorization_revision"],
                "binding_ref": envelope["binding_ref"], "binding_revision": context["binding_revision"],
                "governance_ref": "governance:" + _hash([self.native.generation, source_ref]),
                "governance_revision": state.epochs[kind],
                "retain_until": notice["expires_at"].isoformat(),
            }
            row = (snapshot_ref, _encode(dependency).decode("utf-8"),
                   hashlib.sha256(notice["disclosure"]).hexdigest(), self.native.generation,
                   source_ref, state.epochs[kind])
            self._issued = {ref: item for ref, item in self._issued.items() if item[-1] > time.monotonic()}
            if snapshot_ref not in self._issued and len(self._issued) >= 512:
                raise OwnerFailure("unavailable", "resource_limit")
            with self._database() as db:
                old = db.execute("SELECT * FROM role_snapshot_inputs WHERE snapshot_ref=?", (snapshot_ref,)).fetchone()
                if old and old != row:
                    raise OwnerFailure("rejected", "binding_invalid")
                db.execute("INSERT OR IGNORE INTO role_snapshot_inputs VALUES(?,?,?,?,?,?)", row)
            previous = self._issued.get(snapshot_ref)
            expiry = time.monotonic() + max(0, (notice["expires_at"] - datetime.now(timezone.utc)).total_seconds())
            if previous:
                expiry = min(expiry, previous[-1])
            self._issued[snapshot_ref] = (*row, expiry)
            return dependency

    def inspect(self, invocation, dependency):
        """Metadata-only, under guard. No latest sample can replace an original."""
        claims = self._claims_locked(invocation)
        ref = dependency["reference"]["ref"]
        row = self._issued.get(ref)
        if row is None:
            # A new owner generation has no surviving originals. Querying this
            # metadata never makes an old volatile original available again.
            with self._database() as db:
                saved = db.execute("SELECT generation,dependency_json FROM role_snapshot_inputs WHERE snapshot_ref=?", (ref,)).fetchone()
            if saved and saved[1] == _encode(dependency).decode("utf-8") and saved[0] != self.native.generation:
                return {"availability": "revoked"}
            if (saved and saved[1] == _encode(dependency).decode("utf-8")
                    and datetime.now(timezone.utc) >= datetime.fromisoformat(dependency["retain_until"])):
                return {"availability": "expired"}
            return {"availability": "unverifiable"}
        if row[1] != _encode(dependency).decode("utf-8"):
            return {"availability": "unverifiable"}
        if row[3] != self.native.generation:
            return {"availability": "revoked"}
        envelope = {"scope": claims["scope"], "context": {"caller_ref": claims["caller_ref"],
                    "subject": {"kind": "user", "ref": claims["subject_ref"]},
                    "audience_ref": claims["audience_ref"], "purpose": claims["purpose"], "sharing": claims["sharing"]}}
        if row[2] != hashlib.sha256(_disclosure(envelope)).hexdigest():
            return {"availability": "unverifiable"}
        state = self.native._users[claims["user_id"]]
        kind = next((kind for kind in state.epochs
                     if self.native.source_ref(claims["user_id"], kind) == row[4]), None)
        if (kind is None or state.epochs[kind] != row[5]
                or dependency["access_ref"] != claims["authorization_ref"]
                or dependency["access_revision"] != state.authorization_revision
                or dependency["binding_revision"] != state.binding_revision):
            return {"availability": "revoked"}
        availability = "available"
        if (time.monotonic() >= row[-1]
                or datetime.now(timezone.utc) >= datetime.fromisoformat(dependency["retain_until"])):
            availability = "expired"
        return {"availability": availability, "access_revision": state.authorization_revision,
                "binding_revision": state.binding_revision, "governance_revision": state.epochs[kind],
                "retain_until": dependency["retain_until"]}

    def register(self, invocation, registration):
        self.prepare(invocation)
        with self.guard(invocation):
            claims = self._claims_locked(invocation)
            scope = claims["scope"]
            role_owner = "role-owner:" + _hash([scope[key] for key in
                ("ecosystem_id", "installation_id", "bot_id", "persona_id")])
            if registration["target"]["owner_ref"] != role_owner:
                raise OwnerFailure("rejected", "access_denied")
            dependency = registration["dependency"]
            state = self.inspect(invocation, dependency)
            if state["availability"] != "available":
                return None
            # Exact target includes Role owner/work/part/revision. A reused key
            # with different content is rejected, including after reopen.
            row = (registration["registration_id"], _hash(registration), dependency["reference"]["ref"],
                   _encode(registration["target"]).decode("utf-8"), _hash(dependency), state["governance_revision"])
            with self._database() as db:
                old = db.execute("SELECT * FROM role_snapshot_registrations WHERE registration_id=?", (row[0],)).fetchone()
                if old and old != row:
                    raise OwnerFailure("rejected", "binding_invalid")
                db.execute("INSERT OR IGNORE INTO role_snapshot_registrations VALUES(?,?,?,?,?,?)", row)
            return {"registration_id": row[0], "dependency_sha256": row[4], "governance_revision": row[5]}
