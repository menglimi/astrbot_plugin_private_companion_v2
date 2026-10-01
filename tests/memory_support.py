from dataclasses import replace

from companion_v2.execution.models import digest
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from companion_v2.identity_policy.personas import PersonaBinding, PersonaSelector, SelectorKind
from companion_v2.memory.models import Proposal, AtomRef
from companion_v2.memory.writer import MemoryWriter
from companion_v2.memory.query import MemoryQuery
from tests.test_conversation_messages import MessageFixture


class MemoryFixture(MessageFixture):
    def setUp(self):
        super().setUp()
        self.memory = MemoryWriter(self.tasks)
        self.recall = MemoryQuery(self.memory)

    def alternate_context(self, *, bot_id, role_id, session_selector=False):
        original = self.context.scope
        same_bot = bot_id == original.bot_id
        scope = replace(original, bot_id=bot_id,
                        account_id=original.account_id if same_bot else "login-" + bot_id,
                        native_scope_id=original.native_scope_id if same_bot else "native-" + bot_id,
                        conversation_id=original.conversation_id if same_bot else "conversation-" + bot_id,
                        session_id="session-persona" if same_bot else "session-" + bot_id)
        actor = self.important
        if not same_bot:
            principal = replace(actor.principal, bot_id=bot_id, account_id=scope.account_id)
            self.identity.bind(binding_id="memory-owner-" + bot_id, principal=principal, subject=actor.subject,
                               valid_from=self.clock.now(), expected_revision=self.identity.revision)
            actor = self.identity.resolve_authenticated(principal, observed_at=self.clock.now()).unwrap()
        selector = (PersonaSelector(original.installation_id, SelectorKind.SESSION,
                    bot_id=bot_id, platform=scope.platform, account_id=scope.account_id,
                    conversation_kind=scope.kind, conversation_id=scope.conversation_id, session_id=scope.session_id)
                    if session_selector else PersonaSelector(original.installation_id, SelectorKind.BOT, bot_id=bot_id))
        self.personas.set_binding(PersonaBinding("memory-persona-" + bot_id + "-" + role_id, selector,
            SubjectRef(original.installation_id, SubjectKind.BOT, role_id), 10,
            self.clock.now(), "test", "test"), expected_revision=0, observed_at=self.clock.now())
        return self.context_for(actor, scope)

    def other_memory_owners(self):
        return {
            "bot": self.alternate_context(bot_id="bot-b", role_id=self.context.role_binding.role.subject_id),
            "persona": self.alternate_context(bot_id=self.context.scope.bot_id, role_id="persona-b",
                                              session_selector=True),
        }

    def evidence(self, identifier="我不喝咖啡"):
        event = self.event(identifier)
        if len(event.event_id) > 512:
            # Long-source fixtures preserve their complete payload and source;
            # a platform message identifier is an independent opaque value.
            event = replace(event, event_id="memory-fixture-" + digest(identifier))
        self.accept(event)
        return self.memory.access.capture(self.context, event.source)

    def proposed(self, **changes):
        return Proposal("add", predicate="饮用偏好", object="不喝咖啡", representation="用户说自己不喝咖啡。",
                        evidence=(self.evidence(),), single_value=True, **changes)

    def remember(self, proposal=None, key="save"):
        result = self.memory.submit(self.context, proposal or self.proposed(), operation_key=key).unwrap()
        return AtomRef(result["atom_id"], result["revision"])

    def query(self, query_intent="咖啡", **changes):
        self.recall.begin(self.context, "query")
        return self.recall.query(self.context, "query", query_intent=query_intent, **changes)
