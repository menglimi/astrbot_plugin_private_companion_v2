from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.refs import (
    ReferenceValidationError,
    RoleOwnerRef,
    ScopeKind,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    VersionRef,
)
from companion_v2.role_work.growth import GrowthKind, GrowthState, PersistentRoleGrowthLedger, RoleGrowthRecord
from companion_v2.storage.runtime import StorageRuntime


INSTALLATION = "growth-installation"
BOT = "growth-bot"
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
OWNER = RoleOwnerRef(INSTALLATION, BOT, "role-a")
OTHER_OWNER = RoleOwnerRef(INSTALLATION, BOT, "role-b")
SCOPE = ScopeRef(
    installation_id=INSTALLATION,
    platform="onebot",
    kind=ScopeKind.PRIVATE,
    native_scope_id="private-user-a",
    bot_id=BOT,
    account_id="account-a",
    conversation_id="conversation-a",
    session_id="session-a",
)
ACTOR = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "human-a")
OTHER_ACTOR = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "human-b")


def source(source_id: str = "evidence-a", *, scope: ScopeRef = SCOPE) -> SourceRef:
    return SourceRef(
        source_id=source_id,
        owner="conversation",
        scope=scope,
        version=VersionRef(f"lineage-{source_id}", 1),
        issued_at=NOW,
    )


def growth(
    *,
    growth_id: str = "growth-a",
    owner: RoleOwnerRef = OWNER,
    kind: GrowthKind = GrowthKind.GOAL,
    scope: ScopeRef = SCOPE,
    title: str = "Learn watercolor",
    evidence: tuple[SourceRef, ...] | None = None,
) -> RoleGrowthRecord:
    return RoleGrowthRecord(
        growth_id=growth_id,
        owner=owner,
        scope=scope,
        kind=kind,
        title=title,
        description="Practice landscape studies.",
        progress_note="Collected initial references.",
        sources=(source(),) if evidence is None else evidence,
        created_at=NOW,
        updated_at=NOW,
        proposed_by=ACTOR,
    )


class RoleGrowthStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory(prefix="companion-v2-growth-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.open_runtime()
        self.addCleanup(self._cleanup_runtime)

    def open_runtime(self) -> None:
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.ledger = PersistentRoleGrowthLedger(self.runtime, now=lambda: NOW)

    def close_runtime(self) -> None:
        self.runtime.close()

    def _cleanup_runtime(self) -> None:
        self.close_runtime()

    def reopen(self) -> None:
        self.close_runtime()
        self.open_runtime()

    def test_create_is_idempotent_owner_scoped_and_survives_reopen(self) -> None:
        first = growth()
        self.assertEqual(self.ledger.add(first), first)
        self.assertEqual(self.ledger.add(first), first)

        other_role = growth(owner=OTHER_OWNER, title="Practice pottery")
        self.ledger.add(other_role)
        self.assertEqual(self.ledger.record("growth-a", owner=OTHER_OWNER), other_role)
        self.assertEqual(self.ledger.for_role(OWNER), (first,))
        self.assertEqual(self.ledger.for_role(OTHER_OWNER), (other_role,))
        with self.assertRaises(KeyError):
            self.ledger.record("growth-a", owner=RoleOwnerRef(INSTALLATION, BOT, "role-c"))
        with self.assertRaises(ReferenceValidationError):
            self.ledger.add(growth(title="A different record using the same ID"))

        self.reopen()
        self.assertEqual(self.ledger.record("growth-a", owner=OWNER), first)
        self.assertEqual(self.ledger.revisions("growth-a", owner=OWNER), (first,))

    def test_goal_state_changes_are_explicit_and_operation_replay_is_stable(self) -> None:
        self.ledger.add(growth())
        active = self.ledger.confirm(
            "growth-a", owner=OWNER, scope=SCOPE, expected_revision=1,
            operation_id="confirm-growth-a", actor=ACTOR, observed_at=NOW + timedelta(minutes=1),
        )
        replay = self.ledger.confirm(
            "growth-a", owner=OWNER, scope=SCOPE, expected_revision=1,
            operation_id="confirm-growth-a", actor=ACTOR, observed_at=NOW + timedelta(minutes=2),
        )
        self.assertEqual(replay, active)
        self.assertEqual(active.state, GrowthState.ACTIVE)
        self.assertEqual(active.confirmed_by, ACTOR)

        paused = self.ledger.transition(
            "growth-a", owner=OWNER, scope=SCOPE, expected_revision=2,
            operation_id="pause-growth-a", state=GrowthState.PAUSED, actor=ACTOR,
            observed_at=NOW + timedelta(minutes=3),
        )
        resumed = self.ledger.confirm(
            "growth-a", owner=OWNER, scope=SCOPE, expected_revision=3,
            operation_id="resume-growth-a", actor=OTHER_ACTOR,
            observed_at=NOW + timedelta(minutes=4),
        )
        achieved = self.ledger.transition(
            "growth-a", owner=OWNER, scope=SCOPE, expected_revision=4,
            operation_id="achieve-growth-a", state=GrowthState.ACHIEVED,
            actor=OTHER_ACTOR, observed_at=NOW + timedelta(minutes=5),
        )
        self.assertEqual(paused.state, GrowthState.PAUSED)
        self.assertEqual(resumed.state, GrowthState.ACTIVE)
        self.assertEqual(resumed.confirmed_by, OTHER_ACTOR)
        self.assertEqual(achieved.state, GrowthState.ACHIEVED)
        self.assertEqual(
            tuple(item.state for item in self.ledger.revisions("growth-a", owner=OWNER)),
            (GrowthState.PROPOSED, GrowthState.ACTIVE, GrowthState.PAUSED,
             GrowthState.ACTIVE, GrowthState.ACHIEVED),
        )

    def test_revision_creates_a_fresh_attributed_proposal_and_rejects_stale_revision(self) -> None:
        skill = growth(kind=GrowthKind.SKILL)
        self.ledger.add(skill)
        active = self.ledger.confirm(
            "growth-a", owner=OWNER, scope=SCOPE, expected_revision=1,
            operation_id="confirm-skill", actor=ACTOR, observed_at=NOW + timedelta(minutes=1),
        )
        proposed = self.ledger.revise(
            "growth-a", owner=OWNER, scope=SCOPE, expected_revision=active.revision,
            operation_id="revise-skill", title="Practice watercolor washes",
            description="Explore wet-on-wet and dry brush techniques.",
            progress_note="Started with two color studies.", sources=(source("evidence-b"),),
            actor=OTHER_ACTOR, observed_at=NOW + timedelta(minutes=2),
        )
        self.assertEqual(proposed.revision, 3)
        self.assertEqual(proposed.state, GrowthState.PROPOSED)
        self.assertEqual(proposed.proposed_by, OTHER_ACTOR)
        self.assertIsNone(proposed.confirmed_by)

        with self.assertRaises(ReferenceValidationError):
            self.ledger.transition(
                "growth-a", owner=OWNER, scope=SCOPE, expected_revision=2,
                operation_id="stale-skill-change", state=GrowthState.PAUSED,
                actor=ACTOR, observed_at=NOW + timedelta(minutes=3),
            )
        self.assertEqual(self.ledger.record("growth-a", owner=OWNER), proposed)
        self.assertEqual(len(self.ledger.revisions("growth-a", owner=OWNER)), 3)

    def test_skills_do_not_use_binary_achievement_and_bad_operation_scopes_fail(self) -> None:
        skill = growth(kind=GrowthKind.SKILL)
        self.ledger.add(skill)
        active = self.ledger.confirm(
            "growth-a", owner=OWNER, scope=SCOPE, expected_revision=1,
            operation_id="confirm-skill", actor=ACTOR, observed_at=NOW + timedelta(minutes=1),
        )
        with self.assertRaises(ReferenceValidationError):
            self.ledger.transition(
                "growth-a", owner=OWNER, scope=SCOPE, expected_revision=active.revision,
                operation_id="achieve-skill", state=GrowthState.ACHIEVED,
                actor=ACTOR, observed_at=NOW + timedelta(minutes=2),
            )
        wrong_bot_scope = ScopeRef(
            installation_id=INSTALLATION,
            platform="onebot",
            kind=ScopeKind.PRIVATE,
            native_scope_id="other-bot-private",
            bot_id="other-bot",
            account_id="account-a",
            conversation_id="conversation-a",
            session_id="session-a",
        )
        with self.assertRaises(ReferenceValidationError):
            self.ledger.confirm(
                "growth-a", owner=OWNER, scope=wrong_bot_scope, expected_revision=active.revision,
                operation_id="wrong-scope-confirm", actor=ACTOR,
                observed_at=NOW + timedelta(minutes=2),
            )

    def test_proposals_require_private_same_bot_sources_and_human_attribution(self) -> None:
        group_scope = ScopeRef(
            installation_id=INSTALLATION,
            platform="onebot",
            kind=ScopeKind.GROUP,
            native_scope_id="group-a",
            bot_id=BOT,
            account_id="account-a",
            conversation_id="conversation-a",
            session_id="session-a",
        )
        other_bot_scope = ScopeRef(
            installation_id=INSTALLATION,
            platform="onebot",
            kind=ScopeKind.PRIVATE,
            native_scope_id="other-bot-private",
            bot_id="other-bot",
            account_id="account-a",
            conversation_id="conversation-a",
            session_id="session-a",
        )
        with self.assertRaises(ReferenceValidationError):
            growth(evidence=(source(scope=group_scope),))
        with self.assertRaises(ReferenceValidationError):
            growth(evidence=(source(scope=other_bot_scope),))
        with self.assertRaises(ReferenceValidationError):
            growth(scope=group_scope)
        with self.assertRaises(ReferenceValidationError):
            RoleGrowthRecord(
                growth_id="unattributed-growth",
                owner=OWNER,
                scope=SCOPE,
                kind=GrowthKind.GOAL,
                title="A goal without an attributable proposal",
                description="",
                progress_note="",
                sources=(source(),),
                created_at=NOW,
                updated_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
