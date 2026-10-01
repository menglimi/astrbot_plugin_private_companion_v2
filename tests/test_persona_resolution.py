from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.personas import (
    ConversationRoute, PersonaBinding, PersonaDirectory, PersonaSelector, SelectorKind,
)
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 21, 4, 0, tzinfo=timezone.utc)
INSTALLATION = "persona-installation"
PERSON = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-a")
PRIVATE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "native-private",
                   "bot-a", "login-a", "conversation-a", "session-a")
GROUP = ScopeRef(INSTALLATION, "onebot", ScopeKind.GROUP, "native-group",
                 "bot-a", "login-a", "conversation-g", "session-g")


def role(name):
    return SubjectRef(INSTALLATION, SubjectKind.BOT, name)


class PersonaResolutionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-persona-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.personas = PersonaDirectory(self.runtime)
        self.private = self.personas.register_route(ConversationRoute(PRIVATE, user=PERSON), observed_at=NOW)
        self.group = self.personas.register_route(ConversationRoute(GROUP, group_id="group-a"), observed_at=NOW)

    def selector(self, route, kind):
        return next(selector for selector, _ in route.selectors() if selector.kind is kind)

    def bind(self, identifier, selector, persona, *, precedence=0, at=NOW, until=None,
             overridable=True, authority="admin"):
        binding = PersonaBinding(identifier, selector, role(persona), precedence, at, "test", authority,
                                 overridable, until)
        return self.personas.set_binding(binding, expected_revision=0, observed_at=at)

    def test_private_precedence_is_session_conversation_user_conversation_user_bot_installation(self):
        cases = (
            (SelectorKind.INSTALLATION, "installation"), (SelectorKind.BOT, "bot"),
            (SelectorKind.USER, "user"), (SelectorKind.CONVERSATION, "conversation"),
            (SelectorKind.CONVERSATION_USER, "conversation-user"), (SelectorKind.SESSION, "session"),
        )
        for kind, persona in cases:
            self.bind("binding-" + persona, self.selector(self.private, kind), persona)
            self.assertEqual(self.personas.resolve(PRIVATE, observed_at=NOW).unwrap().binding.role, role(persona))
        result = self.personas.resolve(PRIVATE, observed_at=NOW).unwrap()
        self.assertEqual(result.binding.role, role("session"))
        self.assertGreaterEqual(result.binding.revision, 1)

    def test_group_resolution_never_uses_speaker_user_selector(self):
        private_user = self.selector(self.private, SelectorKind.USER)
        self.bind("private-user", private_user, "private-persona", precedence=99)
        self.bind("group-binding", self.selector(self.group, SelectorKind.GROUP), "group-persona")
        self.assertEqual(self.personas.resolve(GROUP, observed_at=NOW).unwrap().binding.role, role("group-persona"))
        self.assertFalse(any(selector.kind in (SelectorKind.USER, SelectorKind.CONVERSATION_USER)
                             for selector, _ in self.group.selectors()))

    def test_equal_rank_and_precedence_conflict_is_diagnostic(self):
        selector = self.selector(self.private, SelectorKind.CONVERSATION)
        self.bind("first", selector, "one")
        self.bind("second", selector, "two")
        self.assertEqual(self.personas.resolve(PRIVATE, observed_at=NOW).failure.code, "persona_binding_conflict")

    def test_account_namespace_uses_explicit_precedence_and_respects_protected_authority(self):
        selectors = dict((selector.kind, selector) for selector, _ in self.private.selectors())
        broad_bot = PersonaSelector(INSTALLATION, SelectorKind.BOT, bot_id="bot-a")
        self.bind("broad-bot", broad_bot, "broad")
        self.bind("account-bot", selectors[SelectorKind.BOT], "account", precedence=1)
        self.assertEqual(self.personas.resolve(PRIVATE, observed_at=NOW).unwrap().binding.role, role("account"))
        protected = PersonaBinding("protected", broad_bot, role("protected"), 0, NOW, "policy", "owner", False)
        self.personas.set_binding(protected, expected_revision=0, observed_at=NOW)
        self.assertEqual(self.personas.resolve(PRIVATE, observed_at=NOW).unwrap().binding.role, role("protected"))
        with self.assertRaisesRegex(ValueError, "override_denied"):
            self.personas.set_binding(replace(protected, source="other", authority="other", revision=2),
                                      expected_revision=1, observed_at=NOW)

    def test_group_thread_retains_group_persona_and_requires_parent_scene(self):
        thread = replace(GROUP, kind=ScopeKind.THREAD, session_id="thread-a")
        with self.assertRaisesRegex(ValueError, "parent scene"):
            ConversationRoute(thread, group_id="group-a")
        self.personas.register_route(ConversationRoute(thread, group_id="group-a", thread_parent_kind=ScopeKind.GROUP),
                                     observed_at=NOW)
        self.bind("user", self.selector(self.private, SelectorKind.USER), "private", precedence=100)
        self.bind("group", self.selector(self.group, SelectorKind.GROUP), "group")
        self.assertEqual(self.personas.resolve(thread, observed_at=NOW).unwrap().binding.role, role("group"))

    def test_no_reader_during_temporary_period_still_fences_old_role(self):
        self.bind("default", self.selector(self.private, SelectorKind.BOT), "a")
        before = self.personas.resolve(PRIVATE, observed_at=NOW).unwrap().binding
        temporary = PersonaBinding("future", self.selector(self.private, SelectorKind.SESSION), role("b"), 0,
                                    NOW + timedelta(minutes=1), "fixture", "admin",
                                    effective_until=NOW + timedelta(minutes=2))
        self.personas.set_binding(temporary, expected_revision=0, observed_at=NOW)
        self.assertEqual(self.personas.resolve(PRIVATE, observed_at=NOW).unwrap().binding, before)
        after = self.personas.resolve(PRIVATE, observed_at=NOW + timedelta(minutes=3)).unwrap().binding
        self.assertEqual(after.role, before.role)
        self.assertGreater(after.revision, before.revision)

    def test_specific_bindings_do_not_cross_bot_or_account_namespace(self):
        self.bind("installation", self.selector(self.private, SelectorKind.INSTALLATION), "fallback")
        self.bind("private-user", self.selector(self.private, SelectorKind.USER), "private")
        for scope in (replace(PRIVATE, bot_id="bot-b"), replace(PRIVATE, account_id="login-b")):
            self.personas.register_route(ConversationRoute(scope, user=PERSON), observed_at=NOW)
            self.assertEqual(self.personas.resolve(scope, observed_at=NOW).unwrap().binding.role, role("fallback"))

    def test_temporary_binding_falls_back_and_changes_resolution_revision(self):
        self.bind("base", self.selector(self.private, SelectorKind.BOT), "base")
        self.bind("temporary", self.selector(self.private, SelectorKind.SESSION), "temporary",
                  at=NOW, until=NOW + timedelta(minutes=5))
        during = self.personas.resolve(PRIVATE, observed_at=NOW + timedelta(minutes=1)).unwrap().binding
        after = self.personas.resolve(PRIVATE, observed_at=NOW + timedelta(minutes=6)).unwrap().binding
        self.assertEqual((during.role.subject_id, after.role.subject_id), ("temporary", "base"))
        self.assertGreater(after.revision, during.revision)

    def test_switch_away_and_back_fences_original_but_not_another_scope(self):
        self.bind("private-base", self.selector(self.private, SelectorKind.SESSION), "a")
        self.bind("group-base", self.selector(self.group, SelectorKind.SESSION), "group")
        original = self.personas.resolve(PRIVATE, observed_at=NOW).unwrap().binding
        group_original = self.personas.resolve(GROUP, observed_at=NOW).unwrap().binding
        latest = self.personas.binding("private-base")
        self.personas.set_binding(replace(latest, role=role("b"), revision=2), expected_revision=1,
                                  observed_at=NOW + timedelta(seconds=1))
        latest = self.personas.binding("private-base")
        self.personas.set_binding(replace(latest, role=role("a"), revision=3), expected_revision=2,
                                  observed_at=NOW + timedelta(seconds=2))
        current = self.personas.resolve(PRIVATE, observed_at=NOW + timedelta(seconds=3)).unwrap().binding
        self.assertEqual(current.role, original.role)
        self.assertGreater(current.revision, original.revision)
        self.assertEqual(self.personas.resolve(GROUP, observed_at=NOW + timedelta(seconds=3)).unwrap().binding,
                         group_original)

    def test_restart_preserves_route_history_and_exact_binding_adoption_is_explicit(self):
        self.bind("private", self.selector(self.private, SelectorKind.SESSION), "persisted")
        expected = self.personas.resolve(PRIVATE, observed_at=NOW).unwrap().binding
        self.runtime.close()
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.personas = PersonaDirectory(self.runtime)
        self.assertEqual(self.personas.resolve(PRIVATE, observed_at=NOW).unwrap().binding, expected)

        old_scope = replace(PRIVATE, conversation_id="old-conversation", session_id="old-session",
                            native_scope_id="old-window")
        identities = PersistentIdentityDirectory(self.runtime)
        identities.bind_role(scope=old_scope, role=role("old"), expected_revision=0, observed_at=NOW)
        identities.bind_role(scope=old_scope, role=role("middle"), expected_revision=1, observed_at=NOW)
        identities.bind_role(scope=old_scope, role=role("old"), expected_revision=2, observed_at=NOW)
        with self.assertRaisesRegex(ValueError, "adoption_required"):
            self.personas.register_route(ConversationRoute(old_scope, user=PERSON), observed_at=NOW)
        route = self.personas.register_route(ConversationRoute(old_scope, user=PERSON), observed_at=NOW,
                                             adopt_exact_revision=3)
        adopted = self.personas.resolve(old_scope, observed_at=NOW).unwrap().binding
        self.assertEqual((route.initial_revision, adopted.role, adopted.revision), (2, role("old"), 3))


if __name__ == "__main__":
    unittest.main()
