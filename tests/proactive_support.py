"""Synthetic contact ports; no host reload, real provider, or platform traffic."""

from dataclasses import replace
from datetime import timedelta
import json

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.execution.models import TaskContext, digest
from companion_v2.foundation.refs import AudienceRef, SourceRef, VersionRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.proactive.configuration import GROUP, target_for
from companion_v2.proactive.contact_models import ContactIntent
from companion_v2.proactive.models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind
from companion_v2.proactive.service import contact_profile
from companion_v2.sources.models import SourceRecord
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE
from tests.test_role_tool_loop import answered


class ContactFixture(HostFixture):
    def setUp(self):
        super().setUp()
        self.profiles += (contact_profile("primary", max_output_tokens=100),)
        self.registry = FieldRegistry(version="contact-test.v1", fields=configuration_fields(self.profiles))

    def contact_context(self, scope=SCOPE, actor=None):
        actor = actor or self.important
        return TaskContext(actor, self.identity.resolve_role(scope, observed_at=self.clock.now()).unwrap(),
                           AudienceRef(scope, (actor.subject,)))

    def other_window_context(self, identifier="other-window", actor=None):
        actor = actor or self.important
        scope = replace(SCOPE, native_scope_id=identifier, conversation_id="conversation-" + identifier,
                        session_id="session-" + identifier)
        self.personas.register_route(ConversationRoute(scope, user=actor.subject), observed_at=self.clock.now())
        self.grant(actor, scope, "proactive.contact")
        return self.contact_context(scope, actor)

    def preferences(self, app, context=None, at=None):
        return app.proactive.preferences.read(context or self.contact_context(), observed_at=at or self.clock.now()).unwrap()

    def settings(self, app, changes, *, target=None, actor=None, reset=()):
        target = target or target_for(self.contact_context())
        actor = actor or self.important
        snapshot = app.configuration.read(actor, target=target, group_id=GROUP, observed_at=self.clock.now()).unwrap()
        return app.configuration.patch(actor, target=target, group_id=GROUP,
            expected_edit_token=snapshot.edit_token, changes={GROUP + "." + key: value for key, value in changes.items()},
            reset_to_inherit=tuple(GROUP + "." + key for key in reset),
            operation=self.operation(target.authorization_scope, owner=GROUP), observed_at=self.clock.now())

    def opportunity(self, identifier="opportunity", *, scope=SCOPE, expires_at=None):
        return Opportunity(identifier, scope, self.clock.now(), expires_at or self.clock.now() + timedelta(minutes=5))

    def intent(self, opportunity, *, purpose="chat", identifier="thought", sources=(), summary="一个还没发出的念头"):
        return ContactIntent(purpose, Thought(identifier, opportunity, ThoughtKind.CONVERSATION, summary,
            EvidenceSnapshot(opportunity.scope, self.clock.now(), sources), 1.0))

    def source(self, app, identifier="source", *, scope=SCOPE, recipients=None):
        reference = SourceRef(identifier, "conversation.host_input", scope, VersionRef(identifier, 1), NOW)
        body = "用户先前说过：我最近在读一本书。"
        app.proactive.sources.publish(SourceRecord(reference, AudienceRef(scope, recipients or (self.important.subject,)),
            digest(body), body), observed_at=NOW).unwrap()
        return reference

    async def generate(self, envelope):
        self.called.append(envelope)
        if self.model_behavior:
            return await self.model_behavior(envelope)
        return answered(json.dumps({"decision": "send", "text": "想起你上次提到的书，读到哪里了？"}, ensure_ascii=False))

    async def contact(self, app, opportunity=None, intents=None, *, context=None, administrator_test=False):
        context = context or self.contact_context()
        opportunity = opportunity or self.opportunity()
        intents = intents or (self.intent(opportunity),)
        return await app.proactive.contact(context, opportunity, intents,
            role_instruction="这是原角色人格，保持自然。", selection_seed="stable-contact-seed",
            administrator_test=administrator_test)

    async def enabled(self, **options):
        host = await self.start(self.host(**options))
        self.settings(host.application, {"enabled": True}).unwrap()
        return host.application

    async def delivery_state(self, app, task_id, state):
        await self.until(lambda: (app.proactive._delivery_row(task_id) is not None
            and app.proactive._delivery_row(task_id)["state"] == state) or app.state == "faulted")
        self.assertEqual(app.state, "running", app.failure_code)
        return app.proactive._delivery_row(task_id)
