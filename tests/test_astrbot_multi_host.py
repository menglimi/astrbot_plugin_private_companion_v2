import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from astrbot.core.message.components import Video
from astrbot_host.media_components import private_components
from astrbot_host.video.loader import load_native_video
from companion_v2.execution.models import stamp
from companion_v2.memory.models import AtomRef, owner_key
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from tests.multi_host_support import MultiFixture, multi_config
from tests.native_adapter_support import completion
from tests.staging_bootstrap_support import database_contents, wait_for_batch
from tests.memory_stream_support import StreamFixture
from tests.video_support import video_bytes
from astrbot_host.multi_settings import MultiHostSettings
from astrbot_host.multi_api import PREFIX as MULTI_HOST_PREFIX


class _Query(dict):
    """Small Starlette-like query mapping for direct Dashboard handler tests."""

    def getlist(self, key):
        value = self.get(key)
        return [] if value is None else [value]


class MultiSettingsTests(unittest.TestCase):
    def test_conflicting_modes_accounts_and_duplicate_native_personas_are_rejected(self):
        configs = []
        config = multi_config()
        config["staging"]["enabled"] = True
        configs.append(config)
        config = multi_config()
        config["multi_host"]["targets"][1].update(platform_id="qq-main", account_id="100", participant_id="201")
        configs.append(config)
        config = multi_config()
        config["multi_host"]["personas"].append(deepcopy(config["multi_host"]["personas"][0]))
        configs.append(config)
        for config in configs:
            with self.subTest(config=config["multi_host"]["targets"]), self.assertRaises(ValueError):
                MultiHostSettings.parse(config)

    def test_configuration_order_does_not_change_the_stable_installation(self):
        original = multi_config()
        reordered = deepcopy(original)
        reordered["multi_host"]["targets"].reverse()
        reordered["multi_host"]["personas"].reverse()
        self.assertEqual(MultiHostSettings.parse(original), MultiHostSettings.parse(reordered))


class MultiHostTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_routes_bind_each_target_memory_api_and_unregister_cleanly(self):
        self.controller.register_routes()
        registered = {route: handler for route, handler, _, _ in self.native.registered_web_apis}
        expected = {
            MULTI_HOST_PREFIX + suffix
            for suffix in ("/status", "/probe", "/initialize", "/start", "/stop",
                           "/authorize-delivery", "/revoke-delivery")
        }
        self.assertTrue(expected.issubset(registered))
        memory_routes = [route for route in registered if "/targets/" in route and route.endswith("/memory")]
        self.assertEqual(len(memory_routes), 4)
        # Reality 等按动作注册的路由是闭包而非绑定方法；目标绑定断言只看记忆路由。
        memory_handlers = [handler for route, handler in registered.items() if route in memory_routes]
        self.assertEqual({handler.__self__.controller.target_id for handler in memory_handlers},
                         {"first", "second"})
        self.assertTrue(all(handler.__self__.controller.role_id in {"role-a", "role-b"}
                            for handler in memory_handlers))

        request = NS(username="dashboard-admin", query=_Query())
        with patch("astrbot_host.multi_api.request", request), patch("astrbot_host.memory_api.request", request):
            self.assertEqual((await registered[MULTI_HOST_PREFIX + "/status"]())["status"], "ok")
            self.assertEqual((await registered[MULTI_HOST_PREFIX + "/probe"]())["status"], "ok")
            self.assertEqual((await registered[MULTI_HOST_PREFIX + "/initialize"]())["status"], "ok")
            self.assertEqual((await registered[MULTI_HOST_PREFIX + "/start"]())["status"], "ok")
            for route in memory_routes:
                memory_settings = next(
                    handler for path, handler in registered.items()
                    if path == route + "/settings"
                )
                self.assertEqual((await memory_settings())["status"], "ok")
            request.query = _Query({"target_id": "first"})
            authorized = await registered[MULTI_HOST_PREFIX + "/authorize-delivery"]()
            self.assertEqual(authorized["status"], "ok")
            self.assertFalse(authorized["data"]["required"])
            request.query = _Query()
            self.assertEqual((await registered[MULTI_HOST_PREFIX + "/stop"]())["status"], "ok")

        self.controller.unregister_routes()
        self.assertEqual(self.native.registered_web_apis, [])

    async def test_probe_is_read_only_and_initialize_start_use_one_shared_runtime(self):
        before = list(self.root.iterdir())
        self.assertTrue((await self.controller.probe()).is_success)
        self.assertEqual(list(self.root.iterdir()), before)
        app = await self.start_host()
        contexts = []
        for target in ("first", "second"):
            context, _ = await self.accepted(target)
            contexts.append(context)
        self.assertEqual(len(list(self.root.rglob("companion-v2.sqlite3"))), 1)
        self.assertEqual(contexts[0].actor.subject, contexts[1].actor.subject)
        self.assertNotEqual(owner_key(contexts[0]), owner_key(contexts[1]))
        self.assertEqual(app.state, "running")
        # 投递授权已移交按人权限（required: False）：每个目标自己的回复
        # 直达各自的账号与私聊对象，而不是被静默吞掉。
        for platform in self.native.platforms.values():
            self.assertEqual(len(platform.client._api._wsr_api.calls), 1)

    async def test_two_bots_two_personas_keep_facts_and_sources_isolated_after_switch_back(self):
        app = await self.start_host()
        originals, records = {}, {}
        for target in ("first", "second"):
            context, batch = await self.accepted(target)
            originals[target] = context
            records[(target, "role-a")] = self.remember(app, context, batch)
        for target in ("first", "second"):
            self.clock.advance(timedelta(seconds=1))
            self.native.selections[self.controller.settings.target(target).platform_id] = "second"
            context, batch = await self.accepted(target, "persona-b")
            records[(target, "role-b")] = self.remember(app, context, batch)
            original = records[(target, "role-a")]
            self.assertEqual(app.memory.writer.read(context, AtomRef(original["atom_id"], 1)).failure.code, "memory_unavailable")
            self.assertEqual(app.memory.writer.read(originals[target], AtomRef(original["atom_id"], 1)).failure.code,
                             "role_binding_changed")
        self.assertEqual(len({item["operation_id"] for item in records.values()}), 4)
        self.assertEqual(len({item["atom_id"] for item in records.values()}), 4)
        for target in ("first", "second"):
            self.clock.advance(timedelta(seconds=1))
            self.native.selections[self.controller.settings.target(target).platform_id] = "original"
            context, _ = await self.accepted(target, "back-a")
            for (record_target, role), record in records.items():
                result = app.memory.writer.read(context, AtomRef(record["atom_id"], 1))
                self.assertEqual(result.is_success, target == record_target and role == "role-a")
            query_id = "all-" + target
            app.memory.query.begin(context, query_id)
            result = app.memory.query.query(context, query_id, query_intent="咖啡", kind="sources").unwrap()
            self.assertNotIn("persona-b", json.dumps(result))

    async def test_later_native_conversation_recalls_same_owner_but_cannot_resolve_old_pending(self):
        app = await self.start_host()
        context, batch = await self.accepted()
        record = self.remember(app, context, batch)
        pending = self.remember(app, context, batch, key="pending", pending=True)
        self.native.conversations["qq-main"] = "new-conversation"
        self.clock.advance(timedelta(seconds=1))
        later, _ = await self.accepted(identifier="later")
        self.assertEqual(owner_key(context), owner_key(later))
        self.assertTrue(app.memory.writer.read(later, AtomRef(record["atom_id"], 1)).is_success)
        result = app.memory_commands.resolve_pending(later, pending["operation_id"], decision="accept",
            deadline_at=stamp(self.clock.now() + timedelta(seconds=30)))
        self.assertEqual(result["reason_code"], "memory_pending_context_changed")

    async def test_restart_load_preserves_current_context_and_commits_original_pending(self):
        app = await self.start_host()
        context, batch = await self.accepted()
        pending = self.remember(app, context, batch, pending=True)
        await self.controller.terminate()
        self.controller = self.make_controller()
        result = await self.controller.load_existing()
        self.assertTrue(result.is_success, result.failure)
        self.assertFalse(result.unwrap()["started"])
        loaded = self.controller.authority.context("first", "role-a")
        self.assertEqual(context, loaded)
        self.assertTrue((await self.controller.start()).is_success)
        app = self.controller.session.application
        committed = app.memory_commands.resolve_pending(loaded, pending["operation_id"], decision="accept",
            deadline_at=stamp(self.clock.now() + timedelta(seconds=30)))
        self.assertEqual(committed["status"], "succeeded", committed)
        other = self.controller.authority.context("second", "role-a")
        self.assertEqual(app.memory.writer.operation(other, pending["operation_id"]).failure.code,
                         "memory_operation_unavailable")

    async def test_delivery_authorization_is_compatibility_only_and_delivery_follows_each_target(self):
        """正式版移除了按目标投递授权闸门：端点保留为兼容 no-op，投递按各自目标直达。"""
        self.controller = self.make_controller(multi_config(delivery_mode="onebot_private"))
        app = await self.start_host()
        granted = (await self.controller.authorize_delivery("first")).unwrap()
        self.assertEqual((granted["authorized"], granted["required"]), (True, False))
        for target in ("first", "second"):
            await self.accepted(target)
        self.assertEqual(len(self.native.platforms["qq-main"].client._api._wsr_api.calls), 1)
        self.assertEqual(len(self.native.platforms["qq-second"].client._api._wsr_api.calls), 1)
        revoked = (await self.controller.revoke_delivery("first")).unwrap()
        self.assertEqual((revoked["authorized"], revoked["required"]), (True, False))
        await self.accepted("first", "revoked")
        self.assertEqual(len(self.native.platforms["qq-main"].client._api._wsr_api.calls), 2)
        await self.accepted("second", "authorized")
        action, payload = self.native.platforms["qq-second"].client._api._wsr_api.calls[0]
        self.assertEqual((action, payload["self_id"], payload["user_id"]), ("send_private_msg", "101", 200))

    async def test_other_target_can_progress_while_one_native_lookup_is_waiting(self):
        await self.start_host()
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.controller.session.bridge._role
        async def blocked(account, sender):
            if account.bot_id == "bot-a":
                entered.set()
                await release.wait()
            return await original(account, sender)
        self.controller.session.bridge._role = blocked
        task = asyncio.create_task(self.controller.receive_claimed(self.event()))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            result = await asyncio.wait_for(self.controller.receive_claimed(self.event("second")), 2)
            self.assertTrue(result.is_success, result.failure)
        finally:
            release.set()
            self.assertTrue((await task).is_success)

    async def test_rejected_input_cannot_publish_sources_or_grants_for_unconfigured_user(self):
        app = await self.start_host()
        event = self.event()
        event.message_obj.sender.user_id = "201"
        event.session.session_id = "201"
        event.unified_msg_origin = "qq-main:FriendMessage:201"
        before = database_contents(app.runtime)
        self.assertFalse(self.controller.claims(event))
        self.assertEqual((await self.controller.receive_claimed(event)).failure.code, "host_not_claimed")
        self.assertEqual(database_contents(app.runtime), before)

    async def test_identity_remapping_and_persona_rename_are_rejected_as_binding_changes(self):
        await self.start_host()
        context, batch = await self.accepted()
        app = self.controller.session.application
        record = self.remember(app, context, batch)
        await self.controller.terminate()
        changed = multi_config()
        changed["multi_host"]["personas"][0]["role_id"] = "replacement"
        rejected = self.make_controller(changed)
        # 绑定差异检查先于旧的身份映射冲突，并点名变化的绑定类别。
        self.assertEqual((await rejected.initialize_profile()).failure.code, "host_binding_changed")
        await rejected.terminate()
        renamed = multi_config()
        renamed["multi_host"]["personas"][0]["persona_id"] = "renamed"
        self.native.persona_records["renamed"] = {"name": "renamed", "prompt": self.native.persona["prompt"]}
        self.native.selections["qq-main"] = "renamed"
        renamed_controller = self.make_controller(renamed)
        # 人格映射也在绑定契约里：换绑人格同样要重走绑定（见 page-designs/16-setup.md）。
        self.assertEqual((await renamed_controller.initialize_profile()).failure.code, "host_binding_changed")
        await renamed_controller.terminate()
        self.native.selections["qq-main"] = "original"
        self.controller = self.make_controller(multi_config())
        app = await self.start_host()
        current = self.controller.authority.context("first", "role-a")
        self.assertEqual(owner_key(context), owner_key(current))
        self.assertTrue(app.memory.writer.read(current, AtomRef(record["atom_id"], 1)).is_success)

    async def test_revoked_memory_grant_is_not_restored_by_intake_or_reinitialization(self):
        app = await self.start_host()
        context = self.controller.authority.context("first", "role-a")
        identity = self.controller.authority.identities
        identity.revoke_grant(self.controller.authority.grant_id(context.scope, "memory.read"),
            revoked_at=self.clock.now(), expected_revision=identity.revision)
        result = await self.controller.receive_claimed(self.event())
        self.assertEqual(result.failure.code, "authorization_revoked")
        await self.controller.stop()
        result = await self.controller.initialize_profile()
        self.assertEqual(result.failure.code, "authorization_revoked")

    async def test_revoked_dialogue_permission_does_not_break_the_host(self):
        """对话权限是操作员按人收的：收回之后宿主仍要能重开，收信闸负责礼貌拒绝。

        收回前这条链路会在供给阶段直接抛 `authorization_revoked`（既没有对话、
        也没有回话），用户看到的是"插件坏了"。收回 `text` 这类必需能力仍然要硬失败——
        那才是真的配置损坏。
        """
        await self.start_host()
        context = self.controller.authority.context("first", "role-a")
        identity = self.controller.authority.identities
        identifier = self.controller.authority.grant_id(context.scope, "conversation.reply")
        identity.revoke_grant(identifier, revoked_at=self.clock.now(), expected_revision=identity.revision)

        await self.controller.stop()
        self.assertTrue((await self.controller.initialize_profile()).is_success,
                        "收回对话权限后宿主仍应能重开这一次会话")
        # 撤销过的 grant 不能被重开流程悄悄补回来：授权层必须仍然说"已收回"。
        actor = self.controller.authority.actor(self.controller.settings.target("first"))
        access = identity.authorize(actor, scope=context.scope, capability="conversation.reply",
                                    observed_at=self.clock.now())
        self.assertEqual(access.failure.code, "authorization_revoked")

        # 供给路径本身不再把它当故障：上下文仍然可以解析出来（拒绝发生在收信闸）。
        selected = self.controller.authority.select(self.controller.settings.target("first"),
                                                    context.scope, context.role_binding.role)
        self.assertEqual(selected.scope.key, context.scope.key)

    async def test_revoked_required_capability_still_fails_hard(self):
        await self.start_host()
        context = self.controller.authority.context("first", "role-a")
        identity = self.controller.authority.identities
        identity.revoke_grant(self.controller.authority.grant_id(context.scope, "text"),
            revoked_at=self.clock.now(), expected_revision=identity.revision)

        await self.controller.stop()
        result = await self.controller.initialize_profile()
        self.assertEqual(result.failure.code, "authorization_revoked",
                         "必需能力被收回是真故障，不能跟着一起放行")


class MultiHostVideoTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        MultiFixture.setUp(self)
        self.types = NativeAdapterTypes("4.27.2", self.types.event, self.types.provider,
            self.types.function_tool, self.types.tool_set, self.types.reverse_api,
            video=Video, video_loader=load_native_video, component_reader=private_components)
        self.controller = self.make_controller()

    def video_event(self, target):
        config = self.controller.settings.target(target)
        event = self.event(target, identifier="same-message-id", text="这是一段视频")
        locator = "base64://" + base64.b64encode(video_bytes()).decode("ascii")
        event.message_obj.message = [Video(file=locator)]
        event.message_obj.raw_message = dict(post_type="message", message_type="private", sub_type="friend",
            self_id=int(config.account_id), user_id=int(config.participant_id),
            sender={"user_id": int(config.participant_id)}, message_id="same-message-id",
            message=[{"type": "video", "data": {"file": locator}}])
        return event

    async def test_same_native_message_id_keeps_video_sources_isolated_by_account_target(self):
        app = await self.start_host()
        batches = []
        for target in ("first", "second"):
            result = await self.controller.receive_claimed(self.video_event(target))
            self.assertTrue(result.is_success, result.failure)
            batch = result.unwrap()
            await wait_for_batch(self.controller.session, batch)
            batches.append(batch)
        self.assertNotEqual(*batches)
        payloads = app.runtime.read_all("SELECT * FROM conversation_video_payloads ORDER BY source_id", ())
        self.assertEqual(len(payloads), 2)
        self.assertEqual({row["content"] for row in payloads}, {video_bytes()})
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
        for payload, _ in self.native.provider.client.state.calls:
            content = payload["messages"][2]["content"]
            self.assertEqual(len([part for part in content if part["type"] == "image_url"]), 4)
        for platform in self.native.platforms.values():
            self.assertEqual(len(platform.client._api._wsr_api.calls), 1)


if __name__ == "__main__":
    unittest.main()
