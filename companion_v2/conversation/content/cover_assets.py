"""Cover and illustration associations: the host side of the Content↔Image handshake.

The design keeps four things apart, and this module is where that separation lives:

- **the association has its own basis revision.** A cover is attached to a work *and*
  a text version *and* the content hash it was justified against, so "which text was
  this picture drawn for" is answerable later without re-reading the conversation;
- **updating a cover never regenerates or rewrites the text.** The association carries
  the image reference only; the manuscript stays with the provider;
- **an unrelated change may re-attest the same picture, a material change may not.**
  A title-only edit keeps the basis hash, so the owner re-checks the dependency and
  creates a new association at the current revision instead of drawing again; a real
  text change makes the old picture the *old version's* cover, never the new draft's;
- **a late image belongs to the version that asked for it.** A generation that lands
  after the work moved on is stored against its original version, and is never written
  back onto the newer text.

The picture itself is produced by Image (`image.generate`); nothing here generates,
sends or discloses anything. Durable state stays in ``runtime_metadata`` under a key
prefix, so this slice adds no table and no schema version.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from typing import Mapping

from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind
from companion_v2.execution.models import TaskError, digest, stamp

from .authoring_service import GROUP as AUTHORING_GROUP
from .authoring_service import configuration_fields as authoring_fields


GROUP = "content.cover"
OWNER = "configuration"
VERSION = 1
PREFIX = "content.work.cover"
PURPOSES = ("cover", "illustration")

# A cover association carries its own revision, exactly like the design's record table.
STATES = ("active", "historical", "unavailable")


def configuration_fields():
    """Cover options join the authoring group: one Content-creation surface, one owner."""
    return (
        FieldDefinition(AUTHORING_GROUP + ".cover_enabled", AUTHORING_GROUP, AUTHORING_GROUP, ValueKind.BOOLEAN, False,
                        layers=(ConfigLayer.INSTALLATION, ConfigLayer.ROLE),
                        apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER),
        FieldDefinition(AUTHORING_GROUP + ".max_covers_per_work", AUTHORING_GROUP, AUTHORING_GROUP, ValueKind.INTEGER, 2,
                        layers=(ConfigLayer.INSTALLATION, ConfigLayer.ROLE),
                        apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER, minimum=1, maximum=8),
    )


COVER_DEFAULTS = {field.field_id.rsplit(".", 1)[-1]: field.default for field in configuration_fields()}
ALL_FIELDS = authoring_fields() + configuration_fields()


def group_fields():
    """The authoring group's full field set: prose options plus the cover options.

    ``authoring_service`` only owns the prose half and this module only adds the
    cover half, so neither ``configuration_fields()`` is the group contract.
    The coverage audit reads this accessor to compare the whole group at once.
    """
    return ALL_FIELDS


@dataclass(frozen=True)
class CoverIntent:
    """What the caller asked for: attach *this* image to *this* work's version.

    The model names the work, the version it stands on and the image asset it received;
    everything else (scope, owner, whether the picture is still current) is resolved by
    the host. A work with no cover simply has no intent.
    """

    work_id: str
    version_id: str
    asset_id: str
    content_hash: str
    purpose: str = "cover"

    @classmethod
    def from_arguments(cls, arguments):
        """Read one optional cover intent out of a tool call, or return None."""
        if not isinstance(arguments, Mapping):
            return None
        asset_id = arguments.get("cover_asset_id")
        content_hash = arguments.get("cover_content_hash")
        if asset_id is None and content_hash is None:
            return None
        work_id, version_id = arguments.get("work_id"), arguments.get("version_id") or arguments.get("base_version")
        if not all(type(value) is str and value.strip() for value in (work_id, version_id, asset_id, content_hash)):
            raise TaskError("content_cover_invalid", "a cover intent needs its work, version, asset and hash")
        purpose = arguments.get("cover_purpose", "cover")
        if purpose not in PURPOSES:
            raise TaskError("content_cover_invalid", "a cover association needs a known purpose")
        return cls(work_id, version_id, asset_id, content_hash, purpose)

    def asset(self, *, owner, scope, version):
        from companion_v2.foundation.refs import AssetRef
        return AssetRef(self.asset_id, owner, scope, version, self.content_hash)


@dataclass(frozen=True)
class CoverAssociation:
    """One picture attached to one text version, with the basis it was accepted on."""

    association_id: str
    work_id: str
    version_id: str
    basis_hash: str
    purpose: str
    revision: int
    state: str
    attached_at: str
    asset: dict | None = None
    basis_version: str | None = None
    reason: str = ""

    def __post_init__(self):
        if self.purpose not in PURPOSES:
            raise TaskError("content_cover_invalid", "a cover association needs a known purpose")
        if self.state not in STATES:
            raise TaskError("content_cover_invalid", "a cover association needs a known state")
        if type(self.revision) is not int or self.revision < 1:
            raise TaskError("content_cover_invalid", "a cover association needs its own revision")
        if not self.work_id or not self.version_id or not self.basis_hash:
            raise TaskError("content_cover_invalid", "a cover association needs work, version and basis")

    def document(self):
        return {"version": VERSION, "association_id": self.association_id, "work_id": self.work_id,
                "version_id": self.version_id, "basis_hash": self.basis_hash, "basis_version": self.basis_version,
                "purpose": self.purpose, "revision": self.revision, "state": self.state,
                "attached_at": self.attached_at, "asset": self.asset, "reason": self.reason}

    @classmethod
    def restore(cls, value):
        if type(value) is not dict or value.get("version") != VERSION:
            raise TaskError("content_cover_invalid", "stored cover association is unreadable")
        return cls(association_id=value["association_id"], work_id=value["work_id"], version_id=value["version_id"],
                   basis_hash=value["basis_hash"], basis_version=value.get("basis_version"),
                   purpose=value["purpose"], revision=value["revision"], state=value["state"],
                   attached_at=value["attached_at"], asset=value.get("asset"), reason=value.get("reason", ""))


def association_id(*, work_id, version_id, purpose, asset):
    return "cover-" + digest([work_id, version_id, purpose,
                              (asset or {}).get("asset_id"), (asset or {}).get("content_hash")])[:24]


class ContentCoverService:
    """Store cover associations for one relationship, keyed in ``runtime_metadata``."""

    def __init__(self, runtime, *, context):
        self.runtime, self.context = runtime, context

    # -- storage -------------------------------------------------------------

    def key(self, work_id):
        return PREFIX + ":" + digest([VERSION, self.context.key, work_id])

    def _read(self, work_id):
        """Stored state is ``{"head": <current version or null>, "items": [associations]}``.

        The work's current version is recorded explicitly: a cover store cannot infer it
        from its own history, because retiring the last active picture says nothing about
        where the manuscript stands.
        """
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (self.key(work_id),))
        if row is None:
            return {"head": None, "items": []}
        try:
            value = json.loads(row["value"])
        except ValueError:
            return {"head": None, "items": []}
        if type(value) is not dict or value.get("version") != VERSION or type(value.get("items")) is not list:
            return {"head": None, "items": []}
        try:
            items = [CoverAssociation.restore(item) for item in value["items"]]
        except (TaskError, KeyError, TypeError):
            items = []
        head = value.get("head")
        return {"head": head if type(head) is str and head else None, "items": items}

    def _write(self, connection, work_id, state):
        payload = json.dumps({"version": VERSION, "head": state["head"],
                              "items": [item.document() for item in state["items"]]},
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""", (self.key(work_id), payload))

    def settings(self):
        snapshot = SparseConfigurationOwner(self.runtime).read(
            ConfigTarget(self.context.scope.installation_id, ConfigLayer.ROLE, self.context.role_binding.role,
                         bot_id=self.context.scope.bot_id), ALL_FIELDS)
        values = {key.rsplit(".", 1)[-1]: field.value for key, field in snapshot.fields.items()}
        return {"cover_enabled": values.get("cover_enabled", False),
                "max_covers_per_work": values.get("max_covers_per_work", 2)}

    # -- behavior ------------------------------------------------------------

    def list(self, work_id):
        return tuple(self._read(work_id)["items"])

    def head_version(self, work_id):
        """Where the manuscript stands, as last recorded by an association or re-check."""
        return self._read(work_id)["head"]

    def associate(self, *, work_id, version_id, basis_hash, purpose="cover", asset=None, at=None, reason="",
                  settings=None, head_version=None):
        """Attach one picture to a fixed version, or record why it is unavailable.

        The association is current while the work stands on the version the picture was
        drawn for. A picture for any other version stays with the version it was drawn
        for: the design never retargets an old image onto a newer draft. ``head_version``
        is where the manuscript stands now, which is what makes that判断 possible.
        """
        settings = settings or self.settings()
        if not settings["cover_enabled"]:
            raise TaskError("content_cover_disabled", "cover associations are not enabled for this role")
        if purpose not in PURPOSES:
            raise TaskError("content_cover_invalid", "a cover association needs a known purpose")
        state = self._read(work_id)
        head = head_version if head_version is not None else state["head"] or version_id
        current = head == version_id
        if current:
            state["head"] = version_id
        active = [item for item in state["items"] if item.purpose == purpose and item.state == "active"]
        if current and len(active) >= settings["max_covers_per_work"]:
            raise TaskError("content_cover_limit", "this work already carries the allowed number of active pictures")
        now = stamp(at or _now(self.runtime))
        association = CoverAssociation(
            association_id=association_id(work_id=work_id, version_id=version_id, purpose=purpose, asset=asset),
            work_id=work_id, version_id=version_id, basis_hash=basis_hash, basis_version=version_id,
            purpose=purpose, revision=len(state["items"]) + 1,
            state="active" if current else "historical", attached_at=now,
            asset=dict(asset) if asset is not None else None,
            reason=reason if current else (reason or
                "the work has moved to another version; this picture stays with the version it drew"))
        items = [item for item in state["items"] if item.association_id != association.association_id] + [association]
        with self.runtime.transaction() as connection:
            self._write(connection, work_id, {"head": state["head"], "items": items})
        return association

    def record_late(self, *, work_id, version_id, basis_hash, asset, purpose="cover", at=None):
        """Keep an image that arrived after the text moved on, under its own version.

        This is the late-generation path: the original picture belongs to the version
        that asked for it, so it is stored as that version's association instead of
        being written back onto the newer text.
        """
        return self.associate(work_id=work_id, version_id=version_id, basis_hash=basis_hash, purpose=purpose,
                              asset=asset, at=at, head_version="",
                              reason="late result kept with the version that requested it")

    def recheck(self, work_id, *, head_version, head_hash, head_basis=None, at=None):
        """Re-attest the current pictures at the current revision, or retire them.

        ``head_basis`` is the hash of the text *portion the picture depends on* — a
        title-only edit keeps it, a material edit changes it. Same basis ⇒ a new
        association revision at the current version, without drawing again; changed
        basis ⇒ the picture becomes historical and a new one may be proposed.
        """
        state = self._read(work_id)
        if not state["items"]:
            return ()
        now = stamp(at or _now(self.runtime))
        basis = head_hash if head_basis is None else head_basis
        updated, out = [], []
        for item in state["items"]:
            if item.state != "active":
                updated.append(item)
                out.append(item)
                continue
            if item.basis_hash == basis:
                refreshed = replace(item, version_id=head_version, basis_version=head_version,
                                   revision=item.revision + 1, attached_at=now)
            else:
                refreshed = replace(item, revision=item.revision + 1, state="historical", attached_at=now,
                                    reason="the text this picture depended on changed; it stays with its version")
            updated.append(refreshed)
            out.append(refreshed)
        with self.runtime.transaction() as connection:
            self._write(connection, work_id, {"head": head_version, "items": updated})
        return tuple(out)

    def effective(self, work_id):
        """The picture a reader should see now: the current version's, else none."""
        state = self._read(work_id)
        active = [item for item in state["items"]
                  if item.state == "active" and item.asset is not None and item.version_id == state["head"]]
        return active[-1] if active else None


def _now(runtime):
    """The runtime clock when it offers one, else UTC: covers carry their own stamp."""
    clock = getattr(runtime, "now", None)
    return clock() if callable(clock) else datetime.now(timezone.utc)


__all__ = ["ALL_FIELDS", "COVER_DEFAULTS", "ContentCoverService", "CoverAssociation", "CoverIntent", "GROUP",
           "OWNER", "PREFIX", "PURPOSES", "STATES", "VERSION", "association_id", "configuration_fields"]
