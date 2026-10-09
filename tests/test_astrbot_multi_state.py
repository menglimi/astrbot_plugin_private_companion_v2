"""Target/persona state administration through real Dashboard request contexts."""

import asyncio
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from tests.multi_host_support import MultiFixture, multi_config
from tests.group_host_support import group_config
from tests.test_role_state import state_data, calendar_data
from tests.native_adapter_support import completion
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request
from astrbot_host.management_identity import dashboard_operator
from companion_v2.agenda.models import Schedule
from companion_v2.proactive.external_materials import WeatherSnapshot
from companion_v2.execution.models import encode
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy


class MultiStateTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    def register(self):
        self.controller.register_routes()
        self.routes = {path: handler for path, handler, _, _ in self.native.registered_web_apis}
        self.paths = {(target["target_id"], role["role_id"]): role["state_api"]
                      for target in self.controller.web_api.target_inventory() for role in target["roles"]}

    async def initialize(self, config=None):
        if config is not None:
            self.controller = self.make_controller(config)
        self.register()
        result = await self.controller.initialize_profile()
        self.assertTrue(result.is_success, result.failure)
        return self.controller.session.application

    async def request(self, target="first", role="role-a", *, data=None, username="admin", query="", gate=None, suffix=""):
        path = self.paths[(target, role)] + suffix + ("/command" if data is not None else "")
        body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else b""
        async def receive():
            if gate is not None:
                gate[0].set()
                await gate[1].wait()
            return {"type": "http.request", "body": body, "more_body": False}
        native = Request({"type": "http", "method": "POST" if data is not None else "GET", "path": path,
            "headers": [(b"content-type", b"application/json")], "query_string": query.encode("utf-8")}, receive=receive)
        with bind_request_context(PluginRequest(native, username=username)):
            return await self.routes[path]()

    def ok(self, result):
        self.assertEqual(result["status"], "ok", result)
        return result["data"]

    async def status(self, target="first", role="role-a"):
        return self.ok(await self.request(target, role))

    async def configure(self, target="first", role="role-a", *, key="configure", **changes):
        before = await self.status(target, role)
        return self.ok(await self.request(target, role, data=dict(action="configure", operation_key=key,
            edit_token=before["edit_token"], changes=changes)))

    async def state_command(self, target="first", role="role-a", *, action="state.write", key="write", data=None):
        state = (await self.status(target, role))["state"]
        return dict(action=action, operation_key=key, expected_revision=state["revision"],
                    view_token=state["view_token"], **({"data": data} if data is not None else {}))

    async def until(self, predicate):
        async def wait():
            while not predicate():
                await asyncio.sleep(0.01)
        await asyncio.wait_for(wait(), 8)

    async def test_inventory_has_private_state_routes_and_no_group_state_routes(self):
        await self.initialize(group_config())
        private = [path for path in self.paths.values() if path is not None]
        self.assertEqual(len(private), 4)
        for path in private:
            self.assertIn(path, self.routes)
            self.assertIn(path + "/weather", self.routes)
            self.assertIn(path + "/command", self.routes)
        self.assertTrue(all(path is None for (target, _), path in self.paths.items() if target.startswith("group-")))
        self.assertFalse(any("/targets/group-" in path and (path.endswith("/state") or "/state/" in path) for path in self.routes))
        for target in ("first", "second"):
            for role in ("role-a", "role-b"):
                self.assertEqual((await self.status(target, role))["presentation"], {"state": "preview"})

    async def test_weather_route_is_scoped_to_selected_private_role(self):
        app = await self.initialize()
        locations = {
            ("first", "role-a"): ("第一对象城市", 31.2, 121.4),
            ("second", "role-a"): ("第二对象城市", 23.1, 113.3),
        }
        calls = []

        class WeatherPort:
            async def fetch(self, location):
                calls.append(location.name)
                return WeatherSnapshot("open-meteo", location.name, app.now() - timedelta(minutes=5), 22,
                                       "晴", 40, 8, ())

        app.calendar_planning.weather_port = WeatherPort()
        for (target, role), (name, latitude, longitude) in locations.items():
            configured = await self.configure(target, role, key="weather-" + target,
                planning_weather_enabled=True, planning_weather_location=json.dumps({"name":name,
                    "latitude":latitude,"longitude":longitude}, ensure_ascii=False))
            self.assertTrue(configured["operation_id"].startswith("state-config:"))
            response = self.ok(await self.request(target, role, suffix="/weather"))
            self.assertEqual((response["state"], response["location"]), ("live", name))
        self.assertCountEqual(calls, ["第一对象城市", "第二对象城市"])
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertTrue(all(not p.client._api._wsr_api.calls for p in self.native.platforms.values()))

    async def test_two_accounts_two_personas_keep_settings_state_cycle_calendar_and_receipts(self):
        await self.initialize()
        receipts, expected = set(), {}
        for index, (target, role) in enumerate(self.paths):
            label = target + "/" + role
            receipts.add((await self.configure(target, role, enabled=True, calendar_enabled=True, cycle_enabled=True,
                cycle_variation_enabled=bool(index % 2), maintenance_minutes=10 + index))["operation_id"])
            align = await self.state_command(target, role, action="cycle.align", key="align",
                data={"applicability": "applicable", "day": index + 2})
            self.ok(await self.request(target, role, data=align))
            write = await self.state_command(target, role, data=state_data(hunger=label, health="精神不错", sleep="清醒"))
            saved = self.ok(await self.request(target, role, data=write))
            receipts.add(saved["operation_id"])
            self.assertTrue(self.ok(await self.request(target, role, data=write))["replayed"])
            self.assertEqual((await self.request(target, role, data=write | {"operation_key": "stale"}))["data"]["code"],
                             "record_revision_conflict")
            status = await self.status(target, role)
            create = dict(action="calendar.create", operation_key="calendar", expected_revision=0,
                view_token=status["create_token"], id="plan", data=calendar_data(title=label))
            receipts.add(self.ok(await self.request(target, role, data=create))["operation_id"])
            self.assertTrue(self.ok(await self.request(target, role, data=create))["replayed"])
            expected[(target, role)] = (label, index + 2, 10 + index)
        self.assertEqual(len(receipts), 12)
        for (target, role), (label, day, minutes) in expected.items():
            status = await self.status(target, role)
            self.assertEqual(status["state"]["values"]["hunger"], label)
            self.assertEqual(status["state"]["cycle_timeline"]["cycle_day"], day)
            self.assertEqual(status["settings"]["maintenance_minutes"], minutes)
            self.assertEqual([item["title"] for item in status["calendar"]["items"]], [label])
        self.assertEqual(self.native.selections, {"qq-main": "original", "qq-second": "original"})
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertTrue(all(not p.client._api._wsr_api.calls for p in self.native.platforms.values()))

    async def test_foreign_tokens_and_sources_cannot_change_another_target_or_persona(self):
        app = await self.initialize()
        for target, role in self.paths:
            await self.configure(target, role, enabled=True, calendar_enabled=True)
        first = await self.status()
        write = await self.state_command(data=state_data(hunger="想吃点东西"))
        self.ok(await self.request(data=write))
        context = self.controller.authority.context("first", "role-a")
        source = app.role_state.records.get(context, "current")["sources"][0]
        for target, role in (("second", "role-a"), ("first", "role-b")):
            for action in (write, dict(action="calendar.create", operation_key="foreign-calendar",
                    view_token=first["create_token"], expected_revision=0, id="foreign", data=calendar_data())):
                self.assertEqual((await self.request(target, role, data=action))["data"]["code"], "state_view_stale")
            bad_config = dict(action="configure", operation_key="foreign-config", edit_token=first["edit_token"],
                              changes={"typing_enabled": True})
            self.assertEqual((await self.request(target, role, data=bad_config))["data"]["code"], "configuration_revision_conflict")
            own = await self.state_command(target, role, data=state_data(hunger="不应写入"))
            self.assertEqual((await self.request(target, role, data=own | {"sources": [source]}))["data"]["code"],
                             "domain_source_scope")
            self.assertEqual((await self.status(target, role))["state"]["revision"], 0)

    async def test_authentication_and_body_or_query_target_overrides_are_rejected(self):
        await self.initialize()
        before = await self.status()
        body = dict(action="configure", operation_key="enable", edit_token=before["edit_token"], changes={"enabled": True})
        for username in (None, "", "api_key:123"):
            self.assertEqual((await self.request(data=body, username=username))["data"]["code"], "dashboard_identity_required")
        for extra in ({"target_id": "second"}, {"role_id": "role-b"}, {"context": {}}, {"operator": "admin"}):
            self.assertEqual((await self.request(data=body | extra))["data"]["code"], "state_command_invalid")
        for query in ("target_id=second", "role_id=role-b", "limit=1&limit=2"):
            self.assertEqual((await self.request(query=query))["data"]["code"], "state_query_invalid")
            self.assertEqual((await self.request(data=body, query=query))["data"]["code"], "state_command_invalid")
        self.assertEqual((await self.status())["settings"], before["settings"])
        operator = dashboard_operator(self.controller.runtime, "admin", at=self.clock.now())
        policy = ObjectAccessPolicy(self.controller.runtime)
        policy.set_tier(operator.subject, AuthorizationTier.STANDARD, expected_revision=policy.revision, observed_at=self.clock.now())
        self.assertEqual((await self.request(data=body))["data"]["code"], "authorization_denied")

    async def test_public_wording_edit_stays_on_original_role_and_account(self):
        await self.initialize()
        contexts = (("first", "role-a"), ("second", "role-a"), ("first", "role-b"))
        for target, role in contexts:
            await self.configure(target, role, calendar_enabled=True)
            before = await self.status(target, role)
            self.ok(await self.request(target, role, data=dict(action="calendar.create", operation_key="create",
                view_token=before["create_token"], expected_revision=0, id="shared-plan",
                data=calendar_data(title=target + "/" + role))))
        original = (await self.status())["calendar"]["items"][0]
        command = dict(action="calendar.presence", operation_key="public-wording", id=original["id"],
            view_token=original["view_token"], expected_revision=original["revision"], data={"presence": "散步中"})
        for target, role in contexts[1:]:
            self.assertEqual((await self.request(target, role, data=command))["data"]["code"], "state_view_stale")
            unchanged = (await self.status(target, role))["calendar"]["items"][0]
            self.assertEqual((unchanged["revision"], unchanged["presence"]), (1, original["presence"]))
        result = self.ok(await self.request(data=command))
        self.assertFalse(result["replayed"])
        replayed = self.ok(await self.request(data=command))
        self.assertTrue(replayed["replayed"])
        self.assertEqual(replayed["operation_id"], result["operation_id"])
        after = (await self.status())["calendar"]["items"][0]
        self.assertEqual((after["revision"], after["presence"], after["title"]), (2, "散步中", original["title"]))
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertTrue(all(not p.client._api._wsr_api.calls for p in self.native.platforms.values()))

    async def test_awaiting_request_body_cannot_switch_another_requests_target(self):
        await self.initialize()
        first, second = await self.status(), await self.status("second", "role-b")
        body = dict(action="configure", operation_key="parallel", edit_token=first["edit_token"],
                    changes={"maintenance_minutes": 17})
        entered, release = asyncio.Event(), asyncio.Event()
        slow = asyncio.create_task(self.request(data=body, gate=(entered, release)))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            self.ok(await self.request("second", "role-b", data=body | {"edit_token": second["edit_token"],
                                                                       "changes": {"maintenance_minutes": 43}}))
            self.assertEqual((await self.status("second", "role-b"))["settings"]["maintenance_minutes"], 43)
        finally:
            release.set()
            self.ok(await slow)
        self.assertEqual((await self.status())["settings"]["maintenance_minutes"], 17)
        self.assertEqual((await self.status("second", "role-b"))["settings"]["maintenance_minutes"], 43)
        self.assertEqual((await self.status("first", "role-b"))["settings"]["maintenance_minutes"], 30)

    async def test_shared_scheduler_maintains_only_current_personas_and_manual_target(self):
        self.native.selections["qq-second"] = "second"
        app = await self.initialize()
        for target, role in self.paths:
            await self.configure(target, role, enabled=True)
        async def respond(payload, tools):
            second = "你是第二个人格。" in json.dumps(payload, ensure_ascii=False)
            return completion(json.dumps(state_data(hunger="第二人格的状态" if second else "原人格的状态"), ensure_ascii=False))
        self.native.provider.client.state.behavior = respond
        self.assertTrue((await self.controller.start()).is_success)
        contexts = [self.controller.authority.context("first", "role-a"), self.controller.authority.context("second", "role-b")]
        await self.until(lambda: all(app.role_state.records.get(c, "current") for c in contexts))
        self.assertEqual((await self.status())["state"]["values"]["hunger"], "原人格的状态")
        self.assertEqual((await self.status("second", "role-b"))["state"]["values"]["hunger"], "第二人格的状态")
        for target, role in (("first", "role-b"), ("second", "role-a")):
            self.assertEqual((await self.status(target, role))["state"]["revision"], 0)
            body = await self.state_command(target, role, action="maintain", key="manual")
            self.assertEqual((await self.request(target, role, data=body))["data"]["code"], "state_not_enabled")
        body = await self.state_command("second", "role-b", action="maintain", key="manual")
        self.assertEqual(self.ok(await self.request("second", "role-b", data=body))["state"], "scheduled")
        await self.until(lambda: app.role_state.records.get(contexts[1], "current")["revision"] == 2)
        self.assertTrue(self.ok(await self.request("second", "role-b", data=body))["replayed"])
        self.assertEqual(app.role_state.records.get(contexts[0], "current")["revision"], 1)
        self.assertEqual(len(self.native.provider.client.state.calls), 3)
        self.assertIsNone(app.presence)
        self.assertTrue(all(not p.client._api._wsr_api.calls for p in self.native.platforms.values()))
        await self.until(lambda: not app.state_maintenance.workers)
        await self.controller.terminate()
        self.controller = self.make_controller()
        self.register()
        self.assertTrue((await self.controller.load_existing()).is_success)
        self.assertTrue((await self.controller.start()).is_success)
        app = self.controller.session.application
        app.state_maintenance.advance()
        self.assertEqual(app.state_maintenance.workers, {})
        self.assertEqual((await self.status())["state"]["revision"], 1)
        self.assertEqual((await self.status("second", "role-b"))["state"]["revision"], 2)
        self.assertEqual(len(self.native.provider.client.state.calls), 3)

    async def test_switch_back_and_reload_keep_state_cycle_and_calendar_but_expire_old_tokens(self):
        app = await self.initialize()
        await self.configure(calendar_enabled=True, cycle_enabled=True, cycle_variation_enabled=True)
        alignment = await self.state_command(action="cycle.align", key="align", data={"applicability": "applicable", "day": 6})
        self.ok(await self.request(data=alignment))
        self.ok(await self.request(data=await self.state_command(data=state_data(hunger="原人格的记录"))))
        status = await self.status()
        self.ok(await self.request(data=dict(action="calendar.create", operation_key="plan", expected_revision=0,
            view_token=status["create_token"], id="plan", data=calendar_data())))
        self.assertTrue((await self.controller.start()).is_success)
        stale = await self.state_command(key="old-token", data=state_data())
        for selected, role in (("second", "role-b"), ("original", "role-a")):
            self.native.selections["qq-main"] = selected
            await self.accepted(identifier=selected)
            if role == "role-b":
                self.ok(await self.request("first", role, data=await self.state_command("first", role, data=state_data(hunger="第二人格的记录"))))
        self.assertEqual((await self.request(data=stale))["data"]["code"], "state_view_stale")
        saved = await self.status()
        self.assertEqual(saved["state"]["values"]["hunger"], "原人格的记录")
        self.assertEqual(saved["state"]["cycle_timeline"]["cycle_day"], 6)
        self.assertEqual(len(saved["calendar"]["items"]), 1)
        calls = len(self.native.provider.client.state.calls)
        await self.controller.terminate()
        self.controller = self.make_controller()
        self.register()
        self.assertTrue((await self.controller.load_existing()).is_success)
        self.assertTrue((await self.controller.start()).is_success)
        loaded = await self.status()
        self.assertEqual(loaded["state"], saved["state"])
        self.assertEqual(loaded["settings"], saved["settings"])
        self.assertEqual(loaded["calendar"], saved["calendar"])
        self.assertEqual((await self.status("first", "role-b"))["state"]["values"]["hunger"], "第二人格的记录")
        self.assertEqual((await self.status("second"))["state"]["revision"], 0)
        self.assertEqual(len(self.native.provider.client.state.calls), calls)

    async def test_qq_receipts_are_scoped_and_reload_does_not_replay_status(self):
        app = await self.initialize(multi_config(delivery_mode="onebot_private"))
        for target in ("first", "second"):
            await self.configure(target, calendar_enabled=True, presence_enabled=True)
            status = await self.status(target)
            plan = calendar_data(schedule=json.loads(encode(Schedule(self.clock.now(), "Asia/Shanghai"))))
            self.ok(await self.request(target, data=dict(action="calendar.create", operation_key="plan",
                expected_revision=0, view_token=status["create_token"], id="plan", data=plan)))
        self.assertTrue((await self.controller.authorize_delivery("first")).is_success)
        self.assertTrue((await self.controller.start()).is_success)
        contexts = [self.controller.authority.context(target, "role-a") for target in ("first", "second")]
        await self.until(lambda: all(app.presence.results_for(c) for c in contexts))
        for context, target, expected in zip(contexts, ("first", "second"), ("accepted", "not_started")):
            results = (await self.status(target))["presentation"]
            self.assertEqual(set(results), {app.presence.account(context)})
            self.assertEqual(next(iter(results.values()))["state"], expected)
            self.assertEqual((await self.status(target, "role-b"))["presentation"], {})
        first_api = self.native.platforms["qq-main"].client._api._wsr_api
        self.assertEqual([action for action, _ in first_api.calls], ["set_diy_online_status"])
        self.assertEqual(self.native.platforms["qq-second"].client._api._wsr_api.calls, [])
        await self.controller.terminate()
        self.controller = self.make_controller(multi_config(delivery_mode="onebot_private"))
        self.register()
        self.assertTrue((await self.controller.load_existing()).is_success)
        self.assertTrue((await self.controller.start()).is_success)
        app = self.controller.session.application
        await self.until(lambda: all(app.presence.results_for(c) for c in contexts))
        self.assertEqual(len(first_api.calls), 1)
        self.assertEqual(next(iter((await self.status())["presentation"].values()))["state"], "accepted")

    async def test_online_mode_configuration_reaches_the_selected_onebot_account(self):
        app = await self.initialize(multi_config(delivery_mode="onebot_private"))
        await self.configure(enabled=True, online_status_enabled=True)
        command = await self.state_command(data=state_data(online_mode="busy"))
        self.ok(await self.request(data=command))
        self.assertTrue((await self.controller.authorize_delivery("first")).is_success)
        self.assertTrue((await self.controller.start()).is_success)
        context = self.controller.authority.context("first", "role-a")
        await self.until(lambda: bool(app.presence.results_for(context)))
        first_api = self.native.platforms["qq-main"].client._api._wsr_api
        self.assertEqual(first_api.calls, [("set_online_status", {
            "self_id": "100", "status": 50, "ext_status": 0, "battery_status": 0})])
        self.assertEqual(self.native.platforms["qq-second"].client._api._wsr_api.calls, [])
        status = await self.status()
        self.assertEqual(status["presentation_diagnostics"]["online_status"]["state"], "recorded")
        self.assertEqual(status["presentation_diagnostics"]["online_status"]["desired"]["mode"], "busy")
        self.assertEqual(next(iter(status["presentation"].values()))["state"], "accepted")

    async def test_partial_registration_rolls_back_and_old_instance_keeps_replacement_routes(self):
        self.register()
        original_routes = list(self.native.registered_web_apis)
        replacement = self.make_controller()
        original_register = self.native.register_web_api
        def fail_state(route, handler, methods, description):
            original_register(route, handler, methods, description)
            if route.endswith("/state/command"):
                raise RuntimeError("synthetic route failure")
        with patch.object(self.native, "register_web_api", fail_state), self.assertRaises(RuntimeError):
            replacement.register_routes()
        self.assertEqual(self.native.registered_web_apis, original_routes)
        self.assertEqual(replacement.web_api._registered_routes, [])
        replacement.register_routes()
        replacements = list(self.native.registered_web_apis)
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, replacements)
        self.assertEqual((await self.request())["data"]["code"], "staging_host_terminated")
        await replacement.terminate()
        self.assertEqual(self.native.registered_web_apis, [])

    async def test_account_owner_conflict_is_visible_only_to_participating_personas(self):
        app = await self.initialize(multi_config(delivery_mode="onebot_private"))
        for role in ("role-a", "role-b"):
            await self.configure(role=role, calendar_enabled=True, presence_enabled=True)
            status = await self.status(role=role)
            plan = calendar_data(schedule=json.loads(encode(Schedule(self.clock.now(), "Asia/Shanghai"))))
            self.ok(await self.request(role=role, data=dict(action="calendar.create", operation_key="plan",
                expected_revision=0, view_token=status["create_token"], id="plan", data=plan)))
        self.assertTrue((await self.controller.authorize_delivery("first")).is_success)
        self.assertTrue((await self.controller.start()).is_success)
        contexts = [self.controller.authority.context("first", role) for role in ("role-a", "role-b")]
        await self.until(lambda: bool(app.presence.results_for(contexts[0])))
        for role in ("role-a", "role-b"):
            status = await self.status(role=role)
            receipt, = status["presentation"].values()
            self.assertEqual((receipt["state"], receipt["code"]), ("blocked", "multiple_presence_owners"))
            self.assertIn("recorded_at", receipt)
            self.assertEqual(status["presentation_diagnostics"]["custom_status"],
                             {"state": "blocked", "reason": "multiple_presence_owners"})
        self.assertEqual((await self.status("second"))["presentation"], {})
        self.assertTrue(all(not p.client._api._wsr_api.calls for p in self.native.platforms.values()))
        await self.configure(role="role-b", key="stop-competing", presence_enabled=False)
        await self.until(lambda: app.presence.results_for(contexts[0]).get(app.presence.account(contexts[0]), {}).get("state") == "accepted")
        self.assertEqual((await self.status(role="role-b"))["presentation"], {})
        self.assertEqual(len(self.native.platforms["qq-main"].client._api._wsr_api.calls), 1)

    async def test_same_wording_after_persona_switch_does_not_reuse_old_conflict_or_receipt(self):
        app = await self.initialize(multi_config(delivery_mode="onebot_private"))
        for role in ("role-a", "role-b"):
            await self.configure(role=role, calendar_enabled=True, presence_enabled=role == "role-a")
            status = await self.status(role=role)
            plan = calendar_data(schedule=json.loads(encode(Schedule(self.clock.now(), "Asia/Shanghai"))))
            self.ok(await self.request(role=role, data=dict(action="calendar.create", operation_key="plan",
                expected_revision=0, view_token=status["create_token"], id="plan", data=plan)))
        self.assertTrue((await self.controller.authorize_delivery("first")).is_success)
        self.assertTrue((await self.controller.start()).is_success)
        original = self.controller.authority.context("first", "role-a")
        await self.until(lambda: bool(app.presence.results_for(original)))
        receipt, = (await self.status())["presentation"].values()
        self.assertEqual(receipt["state"], "accepted")
        self.assertIn("operation_id", receipt)
        await self.configure(role="role-b", key="competing", presence_enabled=True)
        await self.until(lambda: app.presence.results_for(original).get(app.presence.account(original), {}).get("state") == "blocked")
        self.native.selections["qq-main"] = "second"
        await self.controller.session.synchronize(self.controller.settings.target("first"))
        await app.presence._sync_status()
        self.assertEqual((await self.status(role="role-b"))["presentation"], {})
        diagnostic = (await self.status(role="role-b"))["presentation_diagnostics"]["custom_status"]
        self.assertEqual(diagnostic["state"], "deduplicated")
        self.assertNotIn("operation_id", diagnostic)
        self.assertEqual((await self.status())["presentation"], {})
        self.assertEqual(len(self.native.platforms["qq-main"].client._api._wsr_api.calls), 1)
        self.assertEqual(app.runtime.read_one("SELECT context_key FROM platform_presence_operations", ())["context_key"], original.key)


if __name__ == "__main__":
    unittest.main()
