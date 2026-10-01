from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.refs import (
    AssetRef,
    AudienceRef,
    ReferenceValidationError,
    ScopeKind,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    VersionRef,
)
from companion_v2.identity_policy.directory import IdentityDirectory
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.proactive.models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind
from companion_v2.proactive.planner import ProactivePlanner
from companion_v2.role_work.models import (
    RoleActivity,
    RoleActivityState,
    RoleArtifact,
    RoleArtifactKind,
    RoleLifeLedger,
)
from companion_v2.sharing.models import ShareMaterial, ShareMaterialKind
from companion_v2.sharing.planner import ShareCatalog, SharePlanner
from companion_v2.sources.models import AssetRecord, SourceRecord
from companion_v2.sources.repositories import AssetRepository, SourceRepository
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
INSTALLATION_ID = "installation-alpha"
CAPABILITY = "conversation.read"


def scope() -> ScopeRef:
    return ScopeRef(
        installation_id=INSTALLATION_ID,
        platform="onebot",
        kind=ScopeKind.PRIVATE,
        native_scope_id="private-a",
        bot_id="bot-a", account_id="login-a", conversation_id="conversation-a", session_id="session-a",
    )


def subject() -> SubjectRef:
    return SubjectRef(
        installation_id=INSTALLATION_ID,
        kind=SubjectKind.HUMAN,
        subject_id="subject-a",
    )


def principal() -> AuthenticatedHostPrincipal:
    return AuthenticatedHostPrincipal(
        installation_id=INSTALLATION_ID,
        host_id="astrbot-fixture-host",
        platform="onebot",
        native_account_id="account-a",
        bot_id="bot-a", account_id="login-a",
    )


def policy() -> IdentityDirectory:
    directory = IdentityDirectory()
    directory.bind(
        binding_id="binding-a",
        principal=principal(),
        subject=subject(),
        valid_from=NOW - timedelta(minutes=1),
    )
    directory.issue_grant(
        grant_id="grant-a",
        subject=subject(),
        scope=scope(),
        capability=CAPABILITY,
        tier=AuthorizationTier.IMPORTANT,
        valid_from=NOW - timedelta(minutes=1),
    )
    return directory


def source_reference(*, expires_at: datetime | None = None) -> SourceRef:
    return SourceRef(
        source_id="role-source-a",
        owner="role_work",
        scope=scope(),
        version=VersionRef(lineage_id="role-source-lineage-a", revision=1),
        issued_at=NOW,
        expires_at=expires_at,
    )


def asset_reference() -> AssetRef:
    return AssetRef(
        asset_id="role-asset-a",
        owner="role_work",
        scope=scope(),
        version=VersionRef(lineage_id="role-asset-lineage-a", revision=1),
        content_hash="role-asset-hash-a",
    )


class ProactiveSharingTests(unittest.TestCase):
    def test_large_finite_weights_remain_a_competition_without_sum_overflow(self):
        opportunity = Opportunity("large-weights", scope(), NOW, NOW + timedelta(minutes=1))
        first = Thought("first", opportunity, ThoughtKind.CONVERSATION, "First idea",
                        EvidenceSnapshot(scope(), NOW), 1e308)
        second = replace(first, thought_id="second")
        selected = {ProactivePlanner().select(opportunity, (first, second), observed_at=NOW,
                    selection_seed=str(seed)).unwrap().selected.thought_id for seed in range(20)}
        self.assertEqual(selected, {"first", "second"})

    def test_role_image_becomes_album_material_then_same_share_candidate(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-g5-") as temporary:
            runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id=INSTALLATION_ID,
            )
            sources = SourceRepository(runtime)
            assets = AssetRepository(runtime)
            directory = policy()
            resolved = directory.resolve_authenticated(principal(), observed_at=NOW).unwrap()
            source = source_reference()
            asset = asset_reference()
            audience = AudienceRef(scope=scope(), recipients=(subject(),))
            sources.publish(
                SourceRecord(
                    reference=source,
                    audience=audience,
                    content_hash="role-source-hash-a",
                    payload="a role-owned image creation record",
                ),
                observed_at=NOW,
            ).unwrap()
            assets.publish(AssetRecord(reference=asset, audience=audience), observed_at=NOW).unwrap()

            life = RoleLifeLedger()
            life.add_activity(
                RoleActivity(
                    activity_id="activity-a",
                    role_id="role-a",
                    scope=scope(),
                    started_at=NOW,
                    state=RoleActivityState.ACTIVE,
                )
            )
            artifact = life.add_artifact(
                RoleArtifact(
                    artifact_id="artifact-a",
                    activity_id="activity-a",
                    kind=RoleArtifactKind.IMAGE,
                    source=source,
                    asset=asset,
                    created_at=NOW,
                )
            )
            material = ShareMaterial.from_role_artifact(artifact)
            sharing = SharePlanner(sources=sources, assets=assets, catalog=ShareCatalog())
            candidate = sharing.prepare(
                material,
                role_owner=artifact.owner,
                resolved=resolved,
                capability=CAPABILITY,
                observed_at=NOW,
                authorizer=directory,
            ).unwrap()
            follow_up = sharing.follow_up_material(
                candidate.candidate_id,
                role_owner=artifact.owner,
                resolved=resolved,
                capability=CAPABILITY,
                observed_at=NOW,
                authorizer=directory,
            ).unwrap()

            opportunity = Opportunity(
                opportunity_id="opportunity-a",
                scope=scope(),
                opened_at=NOW,
                expires_at=NOW + timedelta(hours=1),
            )
            thought = Thought(
                thought_id="thought-a",
                opportunity=opportunity,
                kind=ThoughtKind.SHARE,
                summary="Share the completed role-owned image material.",
                evidence=EvidenceSnapshot(
                    scope=scope(),
                    captured_at=NOW,
                    sources=(source,),
                    assets=(asset,),
                ),
                weight=0.01,
                share_candidate=candidate,
            )
            proactive = ProactivePlanner()
            selection = proactive.select(
                opportunity,
                (thought,),
                observed_at=NOW,
                selection_seed="selection-a",
            ).unwrap()
            plan = proactive.plan(selection, created_at=NOW)

            self.assertEqual(follow_up, material)
            self.assertEqual(candidate.material.source, source)
            self.assertEqual(candidate.material.asset, asset)
            self.assertFalse(selection.weight_used)
            self.assertEqual(plan.material_id, material.material_id)
            runtime.close()

    def test_empty_share_and_expired_material_never_become_a_candidate(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-g5-") as temporary:
            runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id=INSTALLATION_ID,
            )
            sources = SourceRepository(runtime)
            assets = AssetRepository(runtime)
            directory = policy()
            resolved = directory.resolve_authenticated(principal(), observed_at=NOW).unwrap()
            sharing = SharePlanner(sources=sources, assets=assets, catalog=ShareCatalog())

            empty = sharing.prepare(
                None,
                resolved=resolved,
                capability=CAPABILITY,
                observed_at=NOW,
                authorizer=directory,
            )
            expired_source = source_reference(expires_at=NOW + timedelta(seconds=1))
            sources.publish(
                SourceRecord(
                    reference=expired_source,
                    audience=AudienceRef(scope=scope(), recipients=(subject(),)),
                    content_hash="expired-source-hash",
                    payload="expired material",
                ),
                observed_at=NOW,
            ).unwrap()
            news = ShareMaterial(
                material_id="news-a",
                kind=ShareMaterialKind.NEWS,
                source=expired_source,
                created_at=NOW,
                published_at=NOW - timedelta(minutes=5),
                fetched_at=NOW,
                external_origin_version="news-origin-version-a",
            )
            expired = sharing.prepare(
                news,
                resolved=resolved,
                capability=CAPABILITY,
                observed_at=NOW + timedelta(minutes=1),
                authorizer=directory,
            )

            self.assertEqual(empty.failure.code, "share_material_required")
            self.assertEqual(expired.failure.code, "source_expired")
            runtime.close()

    def test_weight_is_used_only_when_multiple_feasible_thoughts_compete(self) -> None:
        opportunity = Opportunity(
            opportunity_id="opportunity-a",
            scope=scope(),
            opened_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
        evidence = EvidenceSnapshot(scope=scope(), captured_at=NOW)
        single = Thought(
            thought_id="thought-single",
            opportunity=opportunity,
            kind=ThoughtKind.CONVERSATION,
            summary="A role-owned subjective thought.",
            evidence=evidence,
            weight=0.01,
        )
        other = Thought(
            thought_id="thought-other",
            opportunity=opportunity,
            kind=ThoughtKind.CONVERSATION,
            summary="Another role-owned subjective thought.",
            evidence=evidence,
            weight=99.0,
        )
        proactive = ProactivePlanner()

        only_one = proactive.select(
            opportunity,
            (single,),
            observed_at=NOW,
            selection_seed="selection-a",
        ).unwrap()
        competing = proactive.select(
            opportunity,
            (single, other),
            observed_at=NOW,
            selection_seed="selection-a",
        ).unwrap()

        self.assertEqual(only_one.selected, single)
        self.assertFalse(only_one.weight_used)
        self.assertTrue(competing.weight_used)
        self.assertIn(competing.selected, (single, other))

    def test_share_thought_cannot_exist_without_a_real_candidate(self) -> None:
        opportunity = Opportunity(
            opportunity_id="opportunity-a",
            scope=scope(),
            opened_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
        with self.assertRaises(ReferenceValidationError):
            Thought(
                thought_id="thought-invalid",
                opportunity=opportunity,
                kind=ThoughtKind.SHARE,
                summary="Pretend to share something.",
                evidence=EvidenceSnapshot(scope=scope(), captured_at=NOW),
                weight=1.0,
            )
