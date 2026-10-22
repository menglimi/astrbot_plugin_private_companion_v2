from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_v2.agenda.models import AgendaTarget
from companion_v2.agenda.service import AgendaService
from companion_v2.conversation.foreground import ClaimKind, DraftClaim, ModelDraft
from companion_v2.conversation.tool_loop import LocalRoleTools, ToolSource
from companion_v2.diagnostics.models import DiagnosticContext, DiagnosticQuery
from companion_v2.diagnostics.service import DiagnosticService
from companion_v2.execution.models import Lane, TaskError, encode
from companion_v2.execution.runner import TaskRun
from companion_v2.foundation.refs import ScopeKind
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from companion_v2.model_gateway.budget import BudgetLedger
from companion_v2.model_gateway.models import Amount, BudgetPolicy, ProviderResponse, ToolCall
from companion_v2.model_gateway.routing import ModelRouter
from companion_v2.model_gateway.service import LocalModelGateway
from companion_v2.proactive.external_materials import WeatherSnapshot
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import INSTALLATION, NOW


def call(identifier="save", action="memo.create", **arguments):
    return ToolCall(identifier, action, encode(arguments or {"title": "Private memo", "body": "Private body"}))


def requested(*calls, known=True):
    return ProviderResponse("generated", usage=Amount(15, 40) if known else None,
                            receipt_ref="tool-usage" if known else None, tool_calls=calls)


def answered(text="Saved locally.", claims=()):
    return ProviderResponse("generated", ModelDraft(text, claims), Amount(15, 40), "final-usage")


class WeatherSettingsFixture:
    def __init__(self):
        self.enabled = False
        self.location = ""

    def settings(self, _context):
        return {"planning_weather_enabled": self.enabled,
                "planning_weather_location": self.location,
                "planning_weather_max_age_minutes": 120}, "weather-settings"


class WeatherPortFixture:
    def __init__(self, now):
        self.now = now
        self.locations = []

    async def fetch(self, location):
        self.locations.append(location.name)
        return WeatherSnapshot("qweather", location.name, self.now(), 22.5, "晴", 64, 9, ())


class ToolLoopFixture(MessageFixture):
    def setUp(self):
        super().setUp()
        self.providers = tuple(replace(provider, capabilities=("text", "tools")) for provider in self.providers)
        self.router = ModelRouter(self.configuration, self.profiles, self.providers)
        self.router.start(expected_generation=2)
        self.gateway = LocalModelGateway(self.router, self.ledger, self.tasks)
        self.generator.gateway = self.gateway
        self.diagnostics = DiagnosticService(self.configuration, now=self.clock.now, tasks=self.tasks,
                                             models=self.gateway, messages=self.messages)
        self.weather_settings = WeatherSettingsFixture()
        self.weather_port = WeatherPortFixture(self.clock.now)
        self.tools = LocalRoleTools(self.messages, diagnostics=self.diagnostics,
                                    weather_port=self.weather_port, role_state=self.weather_settings)
        self.agenda = AgendaService(self.runtime)
        self.target = AgendaTarget(self.context.scope, self.context.role_binding.role, self.context.actor.subject)

    def rows(self):
        return self.runtime.read_all("SELECT * FROM conversation_tool_calls ORDER BY sequence", ())

    def assert_reply_usage(self, *, held=0, spent=0):
        calls = self.call_rows()
        self.assertEqual(sum(row["reserved_tokens"] for row in calls if row["actual_tokens"] is None), held)
        self.assertEqual(sum(row["actual_tokens"] or 0 for row in calls), spent)
        # Main-chain calls retain receipts and ownership links but do not
        # consume the plugin's auxiliary model budget.
        self.assertTrue(all((row["held_tokens"], row["spent_tokens"]) == (0, 0) for row in self.accounts()))

    async def manual_run(self, *, batch=None):
        batch = batch or self.accept()
        task = self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        claim = self.tasks.claim(Lane.FOREGROUND).unwrap().claim
        self.tasks.begin(claim).unwrap()
        return batch, TaskRun(self.tasks, claim, task)


class RoleToolLoopTests(ToolLoopFixture, unittest.IsolatedAsyncioTestCase):
    async def test_laya_wait_keeps_tool_suggestion_advisory_and_creates_no_visible_parts(self):
        seen_facts = []

        class DecisionService:
            async def decide(self, facts):
                seen_facts.append(facts)
                return {"status": "ok", "decision": {
                    "turn_state": "unfinished", "action": "wait", "reply_intent": "acknowledge",
                    "reply_style": "brief", "reply_form": "text", "segment_mode": "single",
                    "tool_need": "memory", "reason_codes": [],
                }}

        self.messages.laya_decision_resolver = lambda _context: DecisionService()

        async def suggest_tool(_envelope):
            return requested(call())

        self.responses["primary"] = suggest_tool
        batch = await self.generate()

        self.assertEqual(seen_facts[0]["user_text"], "private input input-1")
        self.assertEqual(len(self.called), 0)
        self.assertEqual(self.rows(), ())
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.messages.batch(batch)["presentation_action"], "silent")
        self.assertIsNone(self.messages.batch(batch)["call_id"])

    async def test_laya_clarification_decision_keeps_a_visible_text_reply(self):
        class DecisionService:
            async def decide(self, _facts):
                return {"status": "ok", "decision": {
                    "turn_state": "complete", "action": "clarify", "reply_intent": "ask",
                    "reply_style": "normal", "reply_form": "text", "segment_mode": "single",
                    "tool_need": "none", "reason_codes": [],
                }}

        self.messages.laya_decision_resolver = lambda _context: DecisionService()
        batch = await self.generate()

        self.assertEqual(len(self.called), 1)
        self.assertTrue(self.parts(batch))

    async def test_refreshed_owner_guidance_keeps_the_original_tool_turn_instructions(self):
        augment = self.tools.augment

        def owner_guidance(*args, **kwargs):
            request = augment(*args, **kwargs)
            guidance = "新增的工具结果表达指引。" if self.called else "本轮初始表达指引。"
            return replace(request, instruction=request.instruction + "\n" + guidance)

        async def respond(envelope):
            return requested(call()) if not envelope.tool_history else answered()

        self.responses["primary"] = respond
        with patch.object(self.tools, "augment", side_effect=owner_guidance):
            await self.generate()

        self.assertEqual(len(self.called), 2)
        original, continued = (envelope.original for _, envelope in self.called)
        self.assertTrue(continued.instruction.startswith(original.instruction))
        self.assertIn("新增的工具结果表达指引。", continued.instruction)
        self.assertEqual(continued.event, original.event)
        self.assertEqual(continued.role_binding, original.role_binding)

    async def test_current_weather_is_a_private_on_demand_read_of_the_configured_role_location(self):
        self.weather_settings.enabled = True
        self.weather_settings.location = json.dumps({"name": "苏州", "latitude": 31.3, "longitude": 120.6},
                                                   ensure_ascii=False)
        actions = {tool.action for tool in self.tools.catalog_for(self.context)}
        self.assertIn("weather.current", actions)

        async def respond(envelope):
            if not envelope.tool_history:
                return requested(ToolCall("weather-call", "weather.current", encode({})))
            result = json.loads(envelope.tool_history[0].result_json)
            self.assertEqual(result["state"], "succeeded")
            self.assertEqual(result["effect"], "none")
            self.assertEqual(result["payload"]["role_location"], "苏州")
            self.assertEqual(result["payload"]["condition"], "晴")
            self.assertNotIn("latitude", result["payload"])
            return answered("苏州当前晴，22.5°C。")

        self.responses["primary"] = respond
        await self.generate()
        self.assertEqual(self.weather_port.locations, ["苏州"])
        self.assertEqual(self.rows()[0]["action"], "weather.current")
        self.assertEqual(self.rows()[0]["effect"], "none")

    async def test_current_weather_tool_is_hidden_until_weather_is_enabled_and_located(self):
        self.weather_settings.location = json.dumps({"name": "苏州", "latitude": 31.3, "longitude": 120.6})
        self.assertNotIn("weather.current", {tool.action for tool in self.tools.catalog_for(self.context)})
        self.weather_settings.enabled = True
        self.weather_settings.location = ""
        self.assertNotIn("weather.current", {tool.action for tool in self.tools.catalog_for(self.context)})
        group = SimpleNamespace(scope=SimpleNamespace(kind=ScopeKind.GROUP))
        self.assertEqual(self.tools.weather.catalog_for(group), ())
        self.assertEqual(self.weather_port.locations, [])

    async def test_create_read_continue_keeps_original_role_configuration_and_accounting(self):
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call())
            if len(envelope.tool_history) == 1:
                result = json.loads(envelope.tool_history[0].result_json)
                receipt = json.loads(result["payload_json"])
                self.assertEqual(receipt["delivery"], "not_started")
                self.patch_model(kind="conversation.reply", prompt="Later prompt", provider="fallback")
                return requested(call("read", "memo.read", memo_id=receipt["object_id"]))
            return answered()
        self.responses["primary"] = respond
        batch = await self.generate()
        self.assertEqual([row["effect"] for row in self.rows()], ["committed", "none"])
        self.assertEqual([row["position"] for row in self.call_rows()], [0, 2, 4])
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM agenda_memos", ())), 1)
        self.assertEqual(self.runtime.read_all("SELECT * FROM agenda_reminders", ()), ())
        self.assertEqual([name for name, _ in self.called], ["primary"] * 3)
        for _, envelope in self.called:
            self.assertEqual(envelope.original.role_instruction, "Original role prompt")
            self.assertEqual(envelope.original.role_binding, self.context.role_binding)
            self.assertEqual(envelope.task_prompt, "Reply supplement")
            self.assertEqual(envelope.configuration_token, self.called[0][1].configuration_token)
        self.assert_reply_usage(spent=45)
        await self.deliver_next(batch)
        self.assertEqual(self.history()[0]["text"], "Saved locally.")

    async def test_duplicate_request_returns_original_receipt_without_another_mutation(self):
        async def respond(envelope):
            return requested(call()) if len(envelope.tool_history) < 2 else answered()
        self.responses["primary"] = respond
        await self.generate()
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM agenda_memos", ())), 1)
        exchanges = self.called[-1][1].tool_history
        self.assertEqual(exchanges[0].result_json, exchanges[1].result_json)

    async def test_read_then_edit_keeps_the_original_observation_and_explains_its_own_change(self):
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call("save"))
            if len(envelope.tool_history) == 1:
                receipt = json.loads(json.loads(envelope.tool_history[0].result_json)["payload_json"])
                return requested(call("read", "memo.read", memo_id=receipt["object_id"]))
            if len(envelope.tool_history) == 2:
                receipt = json.loads(json.loads(envelope.tool_history[0].result_json)["payload_json"])
                return requested(call("edit", "memo.edit", memo_id=receipt["object_id"], expected_revision=1,
                                     changes={"title": "Updated by the same turn"}))
            return answered("I saved it, checked it, and updated it.")
        self.responses["primary"] = respond
        batch = await self.generate()
        self.assertEqual([row["action"] for row in self.rows()], ["memo.create", "memo.read", "memo.edit"])
        self.assertEqual(self.parts(batch)[0]["text"], "I saved it, checked it, and updated it.")
        memo = self.runtime.read_one("SELECT record_json FROM agenda_memos LIMIT 1", ())
        self.assertEqual(json.loads(memo["record_json"])["title"], "Updated by the same turn")

    async def test_restart_after_saved_mutation_reuses_the_original_task_and_validates_receipt(self):
        async def respond(envelope):
            return requested(call()) if not envelope.tool_history else answered()
        self.responses["primary"] = respond
        batch = await self.generate()
        call_count = len(self.called)
        runtime = self.open_runtime()
        tasks, messages, delivery = self.components(runtime)
        LocalRoleTools(messages, diagnostics=DiagnosticService(type(self.configuration)(runtime, self.registry), now=self.clock.now))
        task = messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.assertEqual(task.task_id, self.messages.batch(batch)["generation_task_id"])
        self.assertEqual(len(self.called), call_count)
        delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.assertEqual(messages.observe(self.context, batch).unwrap()["tool_calls"][0]["state"], "succeeded")

    async def test_conflicting_call_id_stops_without_replacing_original_operation(self):
        async def respond(envelope):
            return requested(call() if not envelope.tool_history else call(title="Different", body="Changed"))
        self.responses["primary"] = respond
        batch, run = await self.manual_run()
        with self.assertRaises(TaskError) as failure:
            await self.generator.generate(run)
        self.assertEqual(failure.exception.code, "tool_call_conflict")
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.rows()[0]["effect"], "committed")

    async def test_denied_or_malformed_tools_become_actual_failure_material_for_original_role(self):
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call("bad-owner", owner="someone-else", title="x", body="x"),
                                 call("repair", "diagnostics.confirm", proposal_id="not-approved"),
                                 call("missing", "source.read", handle="not-offered"))
            self.assertTrue(all(json.loads(item.result_json)["state"] == "failed" for item in envelope.tool_history))
            return answered("That operation was not completed.")
        self.responses["primary"] = respond
        batch = await self.generate()
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual(self.runtime.read_all("SELECT * FROM agenda_memos", ()), ())
        self.assertEqual(self.parts(batch)[0]["text"], "That operation was not completed.")
        self.assertEqual(self.messages.observe(self.context, batch).unwrap()["tool_calls"][1]["action"], "unregistered")

    async def test_exact_source_read_enters_evidence_and_is_rechecked_before_delivery_and_history(self):
        batch = self.accept()
        source = self.event("device-original", expires_at=NOW + timedelta(minutes=1)).source
        self.tools.offer_sources(self.context, batch, (ToolSource("phone", source, "text"),)).unwrap()
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call("read-phone", "source.read", handle="phone"))
            self.assertIn(source, envelope.original.context.evidence_sources)
            return answered("The original report is available.", (DraftClaim("report", ClaimKind.OBSERVED,
                            "The original report", evidence=source),))
        self.responses["primary"] = respond
        await self.generate(batch=batch)
        await self.deliver_next(batch)
        self.assertTrue(self.history()[0]["body_available"])
        self.messages.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertFalse(self.history()[0]["body_available"])

    async def test_expired_offered_source_returns_failure_without_reading_replacement(self):
        batch = self.accept()
        source = self.event("old", expires_at=NOW + timedelta(seconds=1)).source
        self.tools.offer_sources(self.context, batch, (ToolSource("phone", source, "text"),)).unwrap()
        self.event("new")
        async def respond(envelope):
            if not envelope.tool_history:
                self.clock.advance(timedelta(seconds=2))
                return requested(call("read", "source.read", handle="phone"))
            self.assertEqual(json.loads(envelope.tool_history[0].result_json)["code"], "source_expired")
            return answered("The original report expired.")
        self.responses["primary"] = respond
        await self.generate(batch=batch)
        self.assertNotIn("private input new", self.rows()[0]["result_json"])

    async def test_revoke_during_continuation_discards_draft_but_settles_both_calls(self):
        batch = self.accept()
        source = self.event("phone").source
        self.tools.offer_sources(self.context, batch, (ToolSource("phone", source, "text"),)).unwrap()
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call("read", "source.read", handle="phone"))
            self.messages.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
            return answered("Should never send")
        self.responses["primary"] = respond
        _, run = await self.manual_run(batch=batch)
        with self.assertRaises(TaskError) as failure:
            await self.generator.generate(run)
        self.assertEqual(failure.exception.code, "source_revoked")
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.call_rows()[-1]["state"], "discarded")
        self.assert_reply_usage(spent=30)

    async def test_cancel_after_save_retains_actual_operation_and_unknown_second_usage(self):
        continued = asyncio.Event()
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call())
            continued.set()
            await asyncio.Event().wait()
        self.responses["primary"] = respond
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        work = asyncio.create_task(self.runner().run_once(Lane.FOREGROUND))
        await asyncio.wait_for(continued.wait(), 2)
        self.messages.cancel(self.context, batch).unwrap()
        await asyncio.wait_for(work, 2)
        self.assertEqual(self.rows()[0]["effect"], "committed")
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM agenda_memos", ())), 1)
        self.assertEqual(self.call_rows()[-1]["state"], "unknown")
        self.assertEqual(self.parts(batch), ())
        self.assert_reply_usage(held=30, spent=15)

    async def test_unknown_local_barrier_never_redispatches_and_rolls_back_domain_write(self):
        batch, run = await self.manual_run()
        original = self.messages.request(run)
        session = self.gateway.open_session(run, original, tools=self.tools.catalog)
        self.responses["primary"] = requested(call())
        completion = await session.generate(original)
        dispatch = self.tools._dispatch
        def broken(*args):
            dispatch(*args)
            raise RuntimeError("Synthetic owner crash after write")
        with patch.object(self.tools, "_dispatch", broken):
            with self.assertRaises(RuntimeError):
                self.tools.execute(run, completion.call_id, completion.tool_calls[0])
        self.assertEqual(self.runtime.read_all("SELECT * FROM agenda_memos", ()), ())
        result = self.tools.execute(run, completion.call_id, completion.tool_calls[0])
        self.assertEqual(json.loads(result.result_json)["state"], "unknown")
        self.assertEqual(self.rows()[0]["state"], "unknown")

    async def test_final_round_tool_request_gets_local_notice_without_an_extra_execution(self):
        async def respond(envelope):
            return requested(call("explain-" + str(len(envelope.tool_history)), "diagnostics.explain", topic="operation"))
        self.responses["primary"] = respond
        batch, run = await self.manual_run()
        result = await self.generator.generate(run)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(self.rows()), 8)
        self.assertEqual(len(self.called), 9)
        self.assertEqual(self.called[-1][1].tools, ())
        from companion_v2.conversation.generation import MODEL_FAILURE_NOTICE
        self.assertEqual([part["text"] for part in self.parts(batch)], [MODEL_FAILURE_NOTICE])

    async def test_unknown_usage_remains_reserved_across_successful_continuation(self):
        async def respond(envelope):
            return requested(call(), known=False) if not envelope.tool_history else answered()
        self.responses["primary"] = respond
        await self.generate()
        self.assert_reply_usage(held=30, spent=15)

    async def test_each_tool_round_uses_confirmed_not_started_fallback_and_separate_accounting(self):
        self.patch_model(kind="conversation.reply", fallback="fallback")
        async def primary(envelope):
            return ProviderResponse("not_started", usage=Amount(0, 0), receipt_ref="primary-not-started")
        async def fallback(envelope):
            return requested(call()) if not envelope.tool_history else answered("Fallback continued the original role.")
        self.responses.update(primary=primary, fallback=fallback)
        batch = await self.generate()
        self.assertEqual([name for name, _ in self.called], ["primary", "fallback", "primary", "fallback"])
        self.assertEqual([row["position"] for row in self.call_rows()], [0, 1, 2, 3])
        self.assertEqual(self.parts(batch)[0]["text"], "Fallback continued the original role.")
        self.assert_reply_usage(spent=30)

    async def test_multi_round_main_chain_usage_does_not_consume_plugin_scope_budget(self):
        policy = BudgetPolicy(*(Amount(45, 1000) for _ in range(5)))
        self.ledger = BudgetLedger(self.runtime, policy)
        self.gateway = LocalModelGateway(self.router, self.ledger, self.tasks)
        self.generator.gateway = self.gateway
        async def respond(envelope):
            if len(envelope.tool_history) == 3:
                return answered("All three tool results were received.")
            return requested(call("explain-" + str(len(envelope.tool_history)),
                                  "diagnostics.explain", topic="configuration"))
        self.responses["primary"] = respond
        batch, run = await self.manual_run()
        await self.generator.generate(run)
        self.assertEqual(len(self.rows()), 3)
        self.assert_reply_usage(spent=60)
        self.assertEqual(self.parts(batch)[0]["text"], "All three tool results were received.")

    async def test_tool_catalog_rejects_a_selected_provider_without_tool_capability(self):
        providers = tuple(replace(provider, capabilities=("text",)) for provider in self.providers)
        router = ModelRouter(self.configuration, self.profiles, providers)
        router.start(expected_generation=self.router.generation)
        gateway = LocalModelGateway(router, self.ledger, self.tasks)
        _, run = await self.manual_run()
        with self.assertRaises(TaskError) as failure:
            gateway.open_session(run, self.messages.request(run), tools=self.tools.catalog)
        self.assertEqual(failure.exception.code, "model_capability_mismatch")
        self.assertEqual(self.called, [])

    async def test_restart_without_the_original_tool_owner_cannot_queue_delivery(self):
        async def respond(envelope):
            return requested(call()) if not envelope.tool_history else answered()
        self.responses["primary"] = respond
        batch = await self.generate()
        runtime = self.open_runtime()
        _, _, delivery = self.components(runtime)
        self.assertEqual(delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code,
                         "tool_owner_unavailable")

    async def test_total_tool_material_budget_stops_the_round_without_exposing_a_partial_reply(self):
        calls = tuple(call("large-" + str(index), "diagnostics.explain", topic="configuration") for index in range(5))
        self.responses["primary"] = requested(*calls)
        batch, run = await self.manual_run()
        with patch.object(self.tools, "_dispatch", return_value=(
                {"state": "succeeded", "effect": "none", "payload": "x" * 60000}, None)):
            with self.assertRaises(TaskError) as failure:
                await self.generator.generate(run)
        self.assertEqual(failure.exception.code, "tool_result_too_large")
        self.assertEqual([row["state"] for row in self.rows()], ["succeeded"] * 4 + ["unknown"])
        self.assertEqual(self.parts(batch), ())

    async def test_role_change_after_operation_cannot_generate_or_send_as_new_persona(self):
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call())
            binding = self.personas.binding("base")
            self.personas.set_binding(replace(binding, revision=2, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "other")),
                                      expected_revision=1, observed_at=NOW)
            return answered("Wrong role")
        self.responses["primary"] = respond
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.rows()[0]["effect"], "committed")

    async def test_diagnostic_snapshot_detects_consumer_state_change_after_restart(self):
        async def respond(envelope):
            return requested(call("check", "diagnostics.inspect", check="configuration",
                group_id="model.conversation.reply", configuration_target="current_window")) if not envelope.tool_history else answered("Configuration checked.")
        self.responses["primary"] = respond
        batch = await self.generate()
        runtime = self.open_runtime()
        tasks, messages, delivery = self.components(runtime)
        configuration = type(self.configuration)(runtime, self.registry)
        diagnostics = DiagnosticService(configuration, now=self.clock.now)
        LocalRoleTools(messages, diagnostics=diagnostics)
        self.assertEqual(delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code,
                         "diagnostic_evidence_changed")

    async def test_diagnostic_explanation_survives_restart_until_expiry_and_observation_is_redacted(self):
        async def respond(envelope):
            return requested(call("explain", "diagnostics.explain", topic="configuration")) if not envelope.tool_history else answered("Configuration explained.")
        self.responses["primary"] = respond
        batch = await self.generate()
        runtime = self.open_runtime()
        _, messages, delivery = self.components(runtime)
        diagnostics = DiagnosticService(type(self.configuration)(runtime, self.registry), now=self.clock.now)
        LocalRoleTools(messages, diagnostics=diagnostics)
        delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        projection = self.messages.observe(self.context, batch).unwrap()
        self.assertEqual(projection["tool_calls"][0]["state"], "succeeded")
        for private in ("Configuration explained", "basis_token", "report_id", "private input"):
            self.assertNotIn(private, json.dumps(projection))
        self.clock.advance(timedelta(seconds=61))
        self.assertEqual(delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code,
                         "diagnostic_report_expired")


if __name__ == "__main__":
    unittest.main()
