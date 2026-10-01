from dataclasses import replace
from datetime import timedelta
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
from companion_v2.relationships import (
    EmotionSubject,
    PersistentRelationshipMemoryLedger,
    RelationshipMemory,
    RelationshipMemoryKind,
    RelationshipMemoryState as State,
)
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import INSTALLATION, NOW, SCOPE


HUMAN = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "human-a")
OWNER = RoleOwnerRef(INSTALLATION, SCOPE.bot_id, "persona-a")


class RelationshipMemoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="companion-v2-relationship-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "runtime"
        self.runtime = self.open_runtime()
        self.ledger = PersistentRelationshipMemoryLedger(self.runtime, now=lambda: NOW)
        self.sources = (SourceRef("conversation-a", "conversation", SCOPE,
                                  VersionRef("conversation-a", 1), NOW),)
        self.entry = RelationshipMemory(
            "trust-context", OWNER, HUMAN, SCOPE, RelationshipMemoryKind.CONTEXT,
            "我觉得我们已经能自在地聊一些生活小事。", self.sources, NOW, NOW,
        )

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def transition(self, state, *, revision, operation):
        return self.ledger.transition("trust-context", owner=OWNER, subject=HUMAN, scope=SCOPE,
            expected_revision=revision, operation_id=operation, state=state, actor=HUMAN)

    def test_only_matching_stable_role_and_human_pair_sees_inventory(self):
        self.ledger.add(self.entry)
        other_person = replace(HUMAN, subject_id="human-b")
        other_role = replace(OWNER, persona_id="persona-b")
        self.ledger.add(replace(self.entry, subject=other_person))
        self.ledger.add(replace(self.entry, owner=other_role))
        second_window = replace(SCOPE, native_scope_id="native-second", conversation_id="conversation-second",
                                session_id="session-second")
        self.assertEqual(self.ledger.for_relationship(OWNER, HUMAN), (self.entry,))
        self.assertEqual(self.ledger.for_relationship(OWNER, other_person)[0].subject, other_person)
        self.assertEqual(self.ledger.for_relationship(other_role, HUMAN)[0].owner, other_role)
        self.assertEqual(self.ledger.memory("trust-context", owner=OWNER, subject=HUMAN), self.entry)
        with self.assertRaises(KeyError):
            self.ledger.memory("trust-context", owner=OWNER, subject=replace(HUMAN, subject_id="unknown"))
        # A later update may come from another window while the stable pair remains the owner.
        updated = self.ledger.transition("trust-context", owner=OWNER, subject=HUMAN, scope=second_window,
            expected_revision=1, operation_id="review-second-window", state=State.REVIEWED, actor=HUMAN)
        self.assertEqual(updated.scope, second_window)

    def test_explicit_review_and_adoption_are_versioned_and_replayable(self):
        self.ledger.add(self.entry)
        self.assertEqual(self.ledger.adopted_for_relationship(OWNER, HUMAN), ())
        reviewed = self.transition(State.REVIEWED, revision=1, operation="review-context")
        self.assertEqual((reviewed.state, reviewed.revision), (State.REVIEWED, 2))
        self.assertEqual(reviewed.reviewed_by, HUMAN)
        self.assertEqual(self.transition(State.REVIEWED, revision=1, operation="review-context"), reviewed)
        adopted = self.transition(State.ADOPTED, revision=2, operation="adopt-context")
        self.assertEqual((adopted.state, adopted.revision), (State.ADOPTED, 3))
        self.assertEqual(adopted.adopted_by, HUMAN)
        self.assertEqual(self.ledger.adopted_for_relationship(OWNER, HUMAN), (adopted,))
        self.assertEqual(tuple(item.revision for item in self.ledger.revisions("trust-context", owner=OWNER, subject=HUMAN)),
                         (1, 2, 3))
        with self.assertRaises(ValueError):
            self.transition(State.ADOPTED, revision=3, operation="adopt-context-again")

    def test_revision_reopens_review_and_stale_writes_do_not_replace_active_text(self):
        self.ledger.add(self.entry)
        self.transition(State.REVIEWED, revision=1, operation="review-before-edit")
        active = self.transition(State.ADOPTED, revision=2, operation="adopt-before-edit")
        corrected = self.ledger.revise("trust-context", owner=OWNER, subject=HUMAN, scope=SCOPE,
            expected_revision=active.revision, operation_id="correct-context",
            interpretation="更正：我们近来才开始聊生活小事。",
            sources=(replace(self.sources[0], version=VersionRef("conversation-a", 2)),),
            observed_at=NOW + timedelta(minutes=5))
        self.assertEqual((corrected.state, corrected.revision), (State.PROPOSED, 4))
        self.assertEqual(self.ledger.adopted_for_relationship(OWNER, HUMAN), ())
        self.assertEqual(tuple(item.interpretation for item in self.ledger.revisions("trust-context", owner=OWNER, subject=HUMAN)),
                         (self.entry.interpretation, self.entry.interpretation, self.entry.interpretation,
                          "更正：我们近来才开始聊生活小事。"))
        with self.assertRaises(ValueError):
            self.ledger.transition("trust-context", owner=OWNER, subject=HUMAN, scope=SCOPE,
                expected_revision=3, operation_id="stale-review", state=State.REVIEWED, actor=HUMAN)
        self.assertEqual(self.ledger.memory("trust-context", owner=OWNER, subject=HUMAN), corrected)

    def test_retracted_record_stays_auditable_but_is_not_adopted_or_revisable(self):
        self.ledger.add(self.entry)
        reviewed = self.transition(State.REVIEWED, revision=1, operation="review-for-retract")
        adopted = self.transition(State.ADOPTED, revision=reviewed.revision, operation="adopt-for-retract")
        retracted = self.transition(State.RETRACTED, revision=adopted.revision, operation="retract-memory")
        self.assertEqual(retracted.state, State.RETRACTED)
        self.assertEqual(self.ledger.adopted_for_relationship(OWNER, HUMAN), ())
        self.assertEqual(len(self.ledger.revisions("trust-context", owner=OWNER, subject=HUMAN)), 4)
        with self.assertRaises(ReferenceValidationError):
            self.ledger.revise("trust-context", owner=OWNER, subject=HUMAN, scope=SCOPE,
                expected_revision=retracted.revision, operation_id="revise-retracted",
                interpretation="重新写回", sources=self.sources)

    def test_emotion_episode_names_whose_feeling_is_described(self):
        episode = RelationshipMemory("episode", OWNER, HUMAN, SCOPE, RelationshipMemoryKind.EMOTION_EPISODE,
            "那次我有些紧张，后来感觉对方也放松了。", self.sources, NOW, NOW,
            emotion_subject=EmotionSubject.ROLE)
        self.ledger.add(episode)
        with self.assertRaises(ReferenceValidationError):
            replace(episode, emotion_subject=None)
        with self.assertRaises(ReferenceValidationError):
            RelationshipMemory("bad-scope", OWNER, HUMAN, replace(SCOPE, kind=ScopeKind.GROUP),
                RelationshipMemoryKind.CONTEXT, "note", self.sources, NOW, NOW)

    def test_memory_source_must_keep_its_private_role_scope(self):
        group_source = replace(self.sources[0], scope=replace(SCOPE, kind=ScopeKind.GROUP))
        with self.assertRaises(ReferenceValidationError):
            replace(self.entry, memory_id="group-source", sources=(group_source,))


if __name__ == "__main__":
    unittest.main()
