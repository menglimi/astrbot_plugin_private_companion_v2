"""Content works enter a real role tool loop and retain withdrawal dependencies."""

import asyncio
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.messages import source_from_document
from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.foundation.refs import SourceRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.personas import ConversationRoute, PersonaBinding, PersonaSelector, SelectorKind
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.model_gateway.models import ToolCall
from companion_v2.sources.dependencies import link
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import SourceRepository
from tests.native_content_support import NativeContentFixture
from tests.test_host_application import HostFixture
from tests.test_management_access import INSTALLATION, NOW, SCOPE
from tests.test_role_tool_loop import answered, requested


TEXT = "第一章\r\n  原文缩进。🌙\n\n末行"


def content_results(envelope):
    return [json.loads(material.payload)["native"]["result"] for material in envelope.original.context.materials
            if material.owner == "content.native"]


def call(name, action, arguments):
    return requested(ToolCall(name, "content.work." + action, encode(arguments)))


class NativeContentFlowTests(NativeContentFixture, HostFixture, unittest.IsolatedAsyncioTestCase):
    def result_reference(self, action="read"):
        row = self.runtime.read_one("SELECT result_source_json FROM extension_tool_invocations WHERE action=?",
                                    ("content.work." + action,))
        return source_from_document(json.loads(row["result_source_json"]))

    async def operate(self, host, action, arguments, *, identifier="operation", scope=SCOPE, actor=None):
        async def model(envelope):
            if not envelope.tool_history:
                return call(identifier, action, arguments)
            return answered("本次操作已经核对。")
        self.model_behavior = model
        batch = host.receive(self.event(identifier, scope=scope, actor=actor or self.important)).unwrap()
        state = await self.done(host.application, batch)
        return batch, state

    def creation_model(self, *, draft="已按原角色读到固定版本。", after_read=None):
        async def model(envelope):
            if not envelope.tool_history:
                return call("create", "create", {"title": "本地作品", "work_type": "story",
                    "chapters": [{"chapter_id": "chapter-1", "text": TEXT}]})
            results = content_results(envelope)
            self.current_work = results[0]["receipt"]
            if len(envelope.tool_history) == 1:
                receipt = results[0]["receipt"]
                return call("read", "read", {"work_id": receipt["work_id"], "version_id": receipt["version_id"]})
            self.assertEqual("".join(part["text"] for part in results[-1]["segments"]), TEXT)
            if after_read is not None:
                await after_read(envelope)
            return answered(draft)
        return model

    async def create_and_read(self, host=None, *, draft="已按原角色读到固定版本。"):
        self.model_behavior = self.creation_model(draft=draft)
        host = host or await self.content_host()
        batch = host.receive(self.event()).unwrap()
        state = await self.done(host.application, batch)
        self.assertEqual(state["state"], "complete", (dict(state), self.content_errors,
            [dict(row) for row in self.runtime.read_all("SELECT kind,state,json_extract(record_json, '$.reason') AS reason FROM execution_tasks", ())]))
        rows = self.runtime.read_all("SELECT * FROM extension_tool_invocations ORDER BY created_at, tool_call_id", ())
        self.assertEqual([row["state"] for row in rows], ["succeeded", "succeeded"], self.content_errors)
        create = next(row for row in rows if row["action"] == "content.work.create")
        source = self.runtime.read_one("SELECT payload_json FROM sources WHERE source_id=?",
                                      (json.loads(create["result_source_json"])["source_id"],))
        receipt = json.loads(json.loads(source["payload_json"]))["native"]["result"]["receipt"]
        return host, batch, receipt

    async def test_original_role_creates_and_reads_fixed_version_without_v1(self):
        host, batch, receipt = await self.create_and_read()
        self.assertEqual(len(self.called), 3)
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.runtime.read_all("SELECT * FROM source_dependencies", ()))
        self.assertEqual(host.application.messages.history(self.context(host.application, batch)).unwrap()["items"][0]["text"],
                         "已按原角色读到固定版本。")
        import sys
        self.assertNotIn("astrbot_plugin_private_companion", sys.modules)
        self.assertTrue(receipt["operation_id"])

    async def test_candidate_adoption_and_both_fixed_versions_are_real_role_tools(self):
        first = candidate = None
        async def model(envelope):
            nonlocal first, candidate
            stage = len(envelope.tool_history)
            results = content_results(envelope)
            if stage == 0:
                return call("create", "create", {"title": "版本作品", "work_type": "story",
                    "chapters": [{"chapter_id": "chapter-1", "text": TEXT}]})
            first = first or results[0]["receipt"]
            if stage == 1:
                return call("candidate", "save_candidate", {"work_id": first["work_id"], "base_revision": 1,
                    "base_version": first["version_id"], "chapters": [{"chapter_id": "chapter-1", "text": TEXT + "新稿"}]})
            candidate = candidate or results[1]["receipt"]
            if stage == 2:
                return call("adopt", "adopt", {"work_id": first["work_id"], "version_id": candidate["version_id"], "expected_revision": 1})
            if stage in (3, 4):
                version = first["version_id"] if stage == 3 else candidate["version_id"]
                return call("read-" + str(stage), "read", {"work_id": first["work_id"], "version_id": version})
            if stage == 5:
                self.assertEqual("".join(s["text"] for s in results[3]["segments"]), TEXT)
                self.assertEqual("".join(s["text"] for s in results[4]["segments"]), TEXT + "新稿")
                return call("describe", "describe", {"work_id": first["work_id"]})
            if stage == 6:
                self.assertEqual(results[-1]["head_version"], candidate["version_id"])
                return call("list", "list", {"limit": 10})
            self.assertEqual(results[-1]["items"][0]["revision"], 2)
            return answered("两个固定版本均可核对，新稿已经采用。")
        self.model_behavior = model
        host = await self.content_host()
        batch = host.receive(self.event()).unwrap()
        self.assertEqual((await self.done(host.application, batch, seconds=45))["state"], "complete", self.content_errors)
        self.assertEqual(len(self.called), 8)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM extension_tool_invocations WHERE state='succeeded'", ())[0], 7)

    async def test_forged_owner_in_model_arguments_never_reaches_provider(self):
        async def model(envelope):
            if not envelope.tool_history:
                return call("forge", "create", {"title": "伪造", "work_type": "story", "owner": "another-user",
                    "chapters": [{"chapter_id": "chapter-1", "text": "不得保存"}]})
            return answered("身份参数不能来自模型。")
        self.model_behavior = model
        host = await self.content_host()
        batch = host.receive(self.event()).unwrap()
        await self.done(host.application, batch)
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM extension_tool_invocations", ())[0], 0)

    async def test_another_bot_with_same_role_cannot_read_the_work(self):
        host, _, receipt = await self.create_and_read()
        scope = replace(SCOPE, bot_id="bot-b", account_id="login-b")
        principal = replace(self.important.principal, bot_id="bot-b", account_id="login-b")
        self.identity.bind(binding_id="content-bot-b", principal=principal, subject=self.important.subject,
                           valid_from=NOW, expected_revision=self.identity.revision)
        actor = self.identity.resolve_authenticated(principal, observed_at=NOW).unwrap()
        role = self.window.role
        self.personas.set_binding(PersonaBinding("bot-b-role", PersonaSelector(INSTALLATION, SelectorKind.BOT, bot_id="bot-b"),
            role, 0, NOW, "fixture", "admin"), expected_revision=0, observed_at=NOW)
        self.grant(actor, scope, "text")
        self.content_grants(self.native_registry, scope=scope, actor=actor, acquire=False, role=role)
        await self.operate(host, "read", {"work_id": receipt["work_id"], "version_id": receipt["version_id"]},
                           identifier="cross-bot", scope=scope, actor=actor)
        row = self.runtime.read_one("SELECT state,result_source_json FROM extension_tool_invocations WHERE tool_call_id='cross-bot'", ())
        self.assertEqual((row["state"], row["result_source_json"]), ("unknown", None))
        self.assertNotIn(TEXT, str(self.called[-1].original.context.materials))

    async def test_another_role_on_same_bot_cannot_read_the_work(self):
        host, _, receipt = await self.create_and_read()
        role = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-b")
        self.personas.set_binding(replace(self.personas.binding("base"), revision=2, role=role),
                                 expected_revision=1, observed_at=NOW)
        CapabilityRepository(self.runtime).set_role_enabled(extension_id="content", role=role,
            bot_id=SCOPE.bot_id, enabled=True, expected_revision=0, observed_at=NOW).unwrap()
        await self.operate(host, "read", {"work_id": receipt["work_id"], "version_id": receipt["version_id"]},
                           identifier="cross-role")
        row = self.runtime.read_one("SELECT state,result_source_json FROM extension_tool_invocations WHERE tool_call_id='cross-role'", ())
        self.assertEqual((row["state"], row["result_source_json"]), ("unknown", None))
        self.assertNotIn(TEXT, str(self.called[-1].original.context.materials))

    async def test_another_participant_on_same_bot_and_role_cannot_read_the_work(self):
        host, _, receipt = await self.create_and_read()
        actor = self.person("other-owner", AuthorizationTier.IMPORTANT)
        scope = replace(SCOPE, native_scope_id="other-owner", conversation_id="other-owner", session_id="other-owner")
        self.grant(actor, scope, "text")
        self.content_grants(self.native_registry, scope=scope, actor=actor, acquire=False)
        await self.operate(host, "read", {"work_id": receipt["work_id"], "version_id": receipt["version_id"]},
                           identifier="cross-participant", scope=scope, actor=actor)
        row = self.runtime.read_one("SELECT state,result_source_json FROM extension_tool_invocations WHERE tool_call_id='cross-participant'", ())
        self.assertEqual((row["state"], row["result_source_json"]), ("unknown", None))
        self.assertNotIn(TEXT, str(self.called[-1].original.context.materials))

    async def test_revoked_read_grant_invalidates_cached_body_and_confirmed_history(self):
        host, batch, _ = await self.create_and_read()
        CapabilityRepository(self.runtime).set_authorization(extension_id="content", capability_id="content.work.read",
            subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.REVOKED,
            expected_revision=1, observed_at=NOW).unwrap()
        self.assertFalse(host.application.messages.sources.validate_reference(self.result_reference(), observed_at=NOW).is_success)
        self.assertFalse(host.application.messages.history(self.context(host.application, batch)).unwrap()["items"][0]["body_available"])

    async def test_missing_or_changed_fixed_version_hash_never_becomes_model_material(self):
        host, _, receipt = await self.create_and_read()
        original = self.content_port.execute
        for label, content_hash in (("missing-hash", None), ("wrong-hash", "0" * 64)):
            with self.subTest(case=label):
                async def altered(request, *, before_dispatch):
                    result = await original(request, before_dispatch=before_dispatch)
                    result["result"]["content_hash"] = content_hash
                    return result
                with patch.object(self.content_port, "execute", altered):
                    before = len(self.called)
                    await self.operate(host, "read", {"work_id": receipt["work_id"], "version_id": receipt["version_id"]},
                                       identifier=label)
                row = self.runtime.read_one("""SELECT i.state, i.receipt_ref, s.state AS source_state
                    FROM extension_tool_invocations i JOIN sources s
                    ON s.source_id=json_extract(i.result_source_json, '$.source_id') WHERE i.tool_call_id=?""", (label,))
                self.assertEqual((row["state"], row["source_state"]), ("succeeded", "revoked"))
                self.assertIsNone(row["receipt_ref"])  # A read has no mutation receipt.
                self.assertEqual(len(self.called) - before, 1)

    async def test_input_withdrawal_invalidates_read_material_and_confirmed_history(self):
        host, batch, _ = await self.create_and_read()
        reference = self.called[0].original.event.source
        host.application.messages.sources.revoke(reference, expected_governance_revision=1, observed_at=NOW).unwrap()
        result = host.application.messages.sources.validate_reference(self.result_reference(), observed_at=NOW)
        self.assertFalse(result.is_success)
        self.assertFalse(host.application.messages.history(self.context(host.application, batch)).unwrap()["items"][0]["body_available"])

    async def test_retraction_events_revoke_all_work_derivatives_and_are_idempotent(self):
        host, batch, receipt = await self.create_and_read()
        app = host.application
        context = self.context(app, batch)
        old_read = self.result_reference()
        derived = SourceRef("derived-content", "test.derived", context.scope, VersionRef("derived-content", 1), NOW)
        app.messages.sources.publish(SourceRecord(derived, context.audience, digest(TEXT), TEXT), observed_at=NOW).unwrap()
        link(self.runtime, derived, (old_read,), NOW)
        _, state = await self.operate(host, "retract", {"work_id": receipt["work_id"], "expected_revision": 1})
        self.assertEqual(state["state"], "complete", self.content_errors)
        self.assertEqual(app.messages.sources.validate_reference(derived, observed_at=NOW).failure.code, "source_revoked")
        self.assertEqual(self.native_registry.content.sources.synchronize(), 0)
        events = self.runtime.read_all("SELECT * FROM inbox WHERE consumer LIKE 'content.governance:%'", ())
        self.assertEqual(len(events), 1)
        self.assertFalse(app.messages.history(context).unwrap()["items"][0]["body_available"])

    async def test_closed_internal_lease_and_missing_owner_guard_never_expose_saved_body(self):
        host, _, _ = await self.create_and_read()
        reference = self.result_reference()
        await self.content_lease.aclose()
        self.assertIsNone(self.native_registry.current_declaration(
            "native:astrbot_plugin_private_companion.content:content.work.read"))
        self.assertFalse(host.application.messages.sources.validate_reference(reference, observed_at=NOW).is_success)
        await self.native_registry.aclose()
        self.assertEqual(SourceRepository(self.open_runtime()).validate_reference(reference, observed_at=NOW).failure.code,
                         "source_owner_unavailable")

    def another_session(self):
        scope = replace(SCOPE, conversation_id="content-control", session_id="content-control")
        self.personas.register_route(ConversationRoute(scope, user=self.important.subject), observed_at=NOW)
        self.grant(self.important, scope, "text")
        self.content_grants(self.native_registry, scope=scope, acquire=False)
        return scope

    async def retract_from_session(self, host):
        scope = self.another_session()
        _, state = await self.operate(host, "retract", {"work_id": self.current_work["work_id"], "expected_revision": 1},
                                      identifier="withdraw-work", scope=scope)
        self.assertEqual(state["state"], "complete", self.content_errors)

    async def test_withdrawal_stops_pending_part_without_revoking_sent_receipt(self):
        self.model_behavior = self.creation_model(draft="已经发送的第一段\n尚未发送的旧正文")
        host = await self.content_host(policy=ConversationPolicy(0, 0, 180, 5))
        batch = host.receive(self.event()).unwrap()
        await self.until(lambda: host.application.flow.row(batch)["reason"] == "part_spacing", seconds=10)
        self.assertEqual(len(self.sent), 1)
        await self.retract_from_session(host)
        self.advance(host.application, 5)
        await self.done(host.application, batch)
        self.assertNotIn("尚未发送的旧正文", [item.text for item in self.sent])
        parts = self.runtime.read_all("SELECT state FROM conversation_parts WHERE batch_id=? ORDER BY sequence", (batch,))
        self.assertEqual(parts[0]["state"], "delivered")
        self.assertNotEqual(parts[1]["state"], "delivered")
        history = host.application.messages.history(self.context(host.application, batch)).unwrap()["items"]
        self.assertFalse(history[0]["body_available"])

    async def test_withdrawal_during_model_wait_discards_late_draft_but_keeps_usage(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def wait_for_return(envelope):
            envelope.before_dispatch()
            entered.set()
            await release.wait()
        self.model_behavior = self.creation_model(draft="已经失效的旧作品回复", after_read=wait_for_return)
        host = await self.content_host()
        batch = host.receive(self.event()).unwrap()
        await asyncio.wait_for(entered.wait(), 10)
        await self.retract_from_session(host)
        release.set()
        await self.done(host.application, batch)
        self.assertNotIn("已经失效的旧作品回复", [item.text for item in self.sent])
        parent = host.application.messages.batch(batch)["generation_task_id"]
        call_row = self.runtime.read_one("SELECT * FROM model_calls WHERE task_id=? ORDER BY position DESC LIMIT 1", (parent,))
        self.assertEqual(call_row["state"], "discarded")
        self.assertIsNotNone(call_row["actual_tokens"])
        self.assertIsNotNone(call_row["receipt_ref"])

    async def test_restart_rechecks_saved_version_without_recreating_work(self):
        host, _, receipt = await self.create_and_read()
        reference = self.result_reference()
        await host.application.close()
        self.native_registry.close()
        await self.content_port.close()
        restored = self.open_runtime()
        self.assertEqual(SourceRepository(restored).validate_reference(reference, observed_at=NOW).failure.code,
                         "source_owner_unavailable")
        self.create_content_port(directory=self.content_directory)
        new = self.host(runtime=restored, tool_port=self.native_registry, policy=ConversationPolicy(0, 0, 180, 0))
        self.native_registry.register_catalog(observed_at=NOW).unwrap()
        await self.start(new, 1, 1)
        SourceRepository(restored).validate_reference(reference, observed_at=NOW).unwrap()
        _, state = await self.operate(new, "read", {"work_id": receipt["work_id"], "version_id": receipt["version_id"]},
                                      identifier="after-restart")
        self.assertEqual(state["state"], "complete", self.content_errors)
        self.assertEqual(restored.read_one("SELECT COUNT(*) FROM extension_tool_invocations WHERE action='content.work.create'", ())[0], 1)

    async def test_restart_consumes_missed_withdrawal_without_reactivating_material(self):
        host, _, _ = await self.create_and_read()
        reference = self.result_reference()
        with patch.object(self.native_registry.content.sources, "synchronize", return_value=0):
            await self.retract_from_session(host)
        self.assertEqual(self.runtime.read_one("SELECT state FROM sources WHERE source_id=?", (reference.source_id,))[0], "active")
        self.assertFalse(host.application.messages.sources.validate_reference(reference, observed_at=NOW).is_success)
        await host.application.close()
        self.native_registry.close()
        await self.content_port.close()
        restored = self.open_runtime()
        self.create_content_port(directory=self.content_directory)
        new = self.host(runtime=restored, tool_port=self.native_registry)
        self.native_registry.register_catalog(observed_at=NOW).unwrap()
        self.assertEqual(restored.read_one("SELECT state FROM sources WHERE source_id=?", (reference.source_id,))[0], "revoked")
        self.assertEqual(self.native_registry.content.sources.synchronize(), 0)
        self.assertEqual(len(restored.read_all("SELECT * FROM inbox WHERE consumer LIKE 'content.governance:%'", ())), 1)


class NativeContentContinuationTests(NativeContentFixture, HostFixture, unittest.IsolatedAsyncioTestCase):
    """A read pins the fixed version; the candidate that answers it must reuse it."""

    async def read_fixed_version(self):
        """Create one work, read its fixed version, and answer the model."""
        async def model(envelope):
            if not envelope.tool_history:
                return call("create", "create", {"title": "续写作品", "work_type": "story",
                    "chapters": [{"chapter_id": "chapter-1", "text": TEXT}]})
            results = content_results(envelope)
            receipt = results[0]["receipt"]
            if len(envelope.tool_history) == 1:
                return call("read", "read", {"work_id": receipt["work_id"], "version_id": receipt["version_id"]})
            self.assertEqual("".join(part["text"] for part in results[-1]["segments"]), TEXT)
            return answered("已按原角色读到固定版本。")
        self.model_behavior = model
        host = await self.content_host()
        batch = host.receive(self.event()).unwrap()
        state = await self.done(host.application, batch, seconds=15)
        self.assertEqual(state["state"], "complete", self.content_errors)
        row = self.runtime.read_one("SELECT result_source_json FROM extension_tool_invocations WHERE action='content.work.create'", ())
        source = self.runtime.read_one("SELECT payload_json FROM sources WHERE source_id=?",
                                      (json.loads(row["result_source_json"])["source_id"],))
        receipt = json.loads(json.loads(source["payload_json"]))["native"]["result"]["receipt"]
        return host, batch, receipt

    async def test_a_read_pins_the_version_a_later_candidate_must_reuse(self):
        from companion_v2.conversation.content import access as content_access
        from companion_v2.conversation.content import authoring_service as service
        host, batch, receipt = await self.read_fixed_version()
        context = self.context(host.application, batch)
        stored = content_access.recorded_authoring_request(self.runtime, context, receipt["work_id"])
        self.assertIsNotNone(stored, "a read must pin the version it returned")
        self.assertEqual(stored["base_version"], receipt["version_id"])
        self.assertEqual(stored["action"], "continue")
        # The pinned request names exactly what the adapter will demand on save.
        arguments = {"work_id": receipt["work_id"], "base_version": receipt["version_id"], "base_revision": 1}
        self.assertEqual(service.continuation(stored, arguments).base_version, receipt["version_id"])
        with self.assertRaises(TaskError) as error:
            service.continuation(stored, {**arguments, "base_version": "another-version"})
        self.assertEqual(error.exception.code, "content_authoring_stale_base")

    async def test_the_anchor_seals_the_request_it_was_written_against(self):
        _host, _batch, _receipt = await self.read_fixed_version()
        row = self.runtime.read_one("SELECT payload_json FROM sources WHERE source_id LIKE 'content-work:%' ORDER BY rowid LIMIT 1", ())
        self.assertIsNotNone(row)
        payload = json.loads(json.loads(row["payload_json"]))
        self.assertIn("request", payload)


if __name__ == "__main__":
    unittest.main()
