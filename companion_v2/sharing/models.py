"""Sharing records always point at actual source and optional asset originals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import AssetRef, ReferenceValidationError, RoleOwnerRef, ScopeRef, SourceRef, normalize_utc
from companion_v2.role_work.models import RoleArtifact, RoleArtifactKind


class ShareMaterialKind(str, Enum):
    ROLE_ARTIFACT = "role_artifact"
    CONTENT_WORK = "content_work"
    NEWS = "news"
    EXTERNAL_ITEM = "external_item"


# Kinds that belong to the role rather than to an outside origin. A content work is a
# role-owned manuscript version, so it carries the same owner requirement as an
# artifact while staying distinguishable for later per-kind budgeting and display.
ROLE_OWNED_KINDS = frozenset({ShareMaterialKind.ROLE_ARTIFACT, ShareMaterialKind.CONTENT_WORK})


def _opaque(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    return value


@dataclass(frozen=True)
class ShareMaterial:
    material_id: str
    kind: ShareMaterialKind
    source: SourceRef
    created_at: datetime
    asset: AssetRef | None = None
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    external_origin_version: str | None = None
    role_owner: RoleOwnerRef | None = None

    def __post_init__(self) -> None:
        _opaque(self.material_id, field="material_id")
        if self.kind in ROLE_OWNED_KINDS:
            if self.role_owner is None or (self.role_owner.installation_id != self.source.scope.installation_id
                                           or self.role_owner.bot_id != self.source.scope.bot_id):
                raise ReferenceValidationError("role share material requires its original bot/persona owner")
        elif self.role_owner is not None:
            raise ReferenceValidationError("external material cannot claim a role artifact owner")
        object.__setattr__(self, "created_at", normalize_utc(self.created_at, field="created_at"))
        if self.asset is not None and self.asset.scope != self.source.scope:
            raise ReferenceValidationError("share asset and source must share a scope")
        if self.kind is ShareMaterialKind.NEWS:
            if self.published_at is None or self.fetched_at is None or self.external_origin_version is None:
                raise ReferenceValidationError("news material requires publication, fetch, and origin version")
            _opaque(self.external_origin_version, field="external_origin_version")
            object.__setattr__(
                self,
                "published_at",
                normalize_utc(self.published_at, field="published_at"),
            )
            object.__setattr__(
                self,
                "fetched_at",
                normalize_utc(self.fetched_at, field="fetched_at"),
            )
        elif self.published_at is not None or self.fetched_at is not None or self.external_origin_version is not None:
            raise ReferenceValidationError("only news material may carry external freshness fields")

    @classmethod
    def from_role_artifact(cls, artifact: RoleArtifact) -> "ShareMaterial":
        if artifact.kind is RoleArtifactKind.IMAGE and artifact.asset is None:
            raise ReferenceValidationError("image artifact cannot become share material without its asset")
        return cls(
            material_id=f"artifact-material-{artifact.artifact_id}",
            kind=ShareMaterialKind.ROLE_ARTIFACT,
            source=artifact.source,
            asset=artifact.asset,
            created_at=artifact.created_at,
            role_owner=artifact.owner,
        )

    @classmethod
    def from_content_work(cls, *, source: SourceRef, role_owner: RoleOwnerRef, work_id: str, version_id: str,
                          created_at: datetime, asset: AssetRef | None = None) -> "ShareMaterial":
        """One Content manuscript version as share material.

        The material names the fixed version it discloses, so the invitation a reader
        receives can always be resolved back to that exact text. Sharing an opening line
        never settles the manuscript, and the work may equally stay unshared forever:
        this builder records nothing and sends nothing.
        """
        _opaque(work_id, field="work_id")
        _opaque(version_id, field="version_id")
        if source.scope.installation_id != role_owner.installation_id or source.scope.bot_id != role_owner.bot_id:
            raise ReferenceValidationError("content work material requires its original installation and bot")
        return cls(
            material_id=f"work-material-{work_id}-{version_id}",
            kind=ShareMaterialKind.CONTENT_WORK,
            source=source,
            asset=asset,
            created_at=created_at,
            role_owner=role_owner,
        )

    @property
    def scope(self) -> ScopeRef:
        return self.source.scope


@dataclass(frozen=True)
class ShareCandidate:
    candidate_id: str
    material: ShareMaterial
    target_scope: ScopeRef
    prepared_at: datetime

    def __post_init__(self) -> None:
        _opaque(self.candidate_id, field="candidate_id")
        if self.target_scope != self.material.scope:
            raise ReferenceValidationError("share target must match current material scope")
        object.__setattr__(self, "prepared_at", normalize_utc(self.prepared_at, field="prepared_at"))
