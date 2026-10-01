"""Actual Game receipts traverse role tools and the private experience producer."""

from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_plugin_game_companion.native_v2 import provider as game_provider
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.messages import source_from_document
from companion_v2.execution.models import encode
from companion_v2.model_gateway.models import ToolCall
from tests.test_game_native_blackjack import shoe_with_draws
from tests.test_game_native_xiangqi import FakeEngine
from tests.test_host_application import HostFixture
from tests.test_management_access import SCOPE
from tests.test_role_tool_loop import answered, requested


class GameMemoryTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def create_port(self):
        plugin = SimpleNamespace(native_v2_blackjack_enabled=True, native_v2_xiangqi_enabled=True,
            native_v2_turtle_soup_enabled=True, native_v2_turtle_soup_content_level="all_ages",
            native_v2_turtle_soup_max_hints=3, native_v2_draw_guess_enabled=True,
            native_v2_draw_guess_max_guesses=5, native_v2_draw_guess_duration_seconds=120,
            xiangqi_engine=FakeEngine())
        self.game_port = game_provider.NativeGameProvider(plugin, self.root.parent / "game-provider", version="0.2.8")
        self.addAsyncCleanup(self.game_port.close)
        self.game_star = SimpleNamespace(root_dir_name=game_provider.PLUGIN_ID, version="0.2.8", activated=True,
            star_cls=SimpleNamespace(extension_api=SimpleNamespace(companion_v2_native=lambda: self.game_port)))
        self.native_registry = NativeExtensionRegistry(SimpleNamespace(get_all_stars=lambda: [self.game_star]),
                                                       now=self.clock.now)
        self.addCleanup(self.native_registry.close)

    async def game_host(self):
        self.create_port()
        host = self.host(tool_port=self.native_registry, policy=ConversationPolicy(0, 0, 180, 0))
        self.native_registry.register_catalog(observed_at=self.clock.now()).unwrap()
        repository = CapabilityRepository(self.runtime)
        package = self.native_registry.declarations()[0].descriptor.package
        repository.acquire(extension_id="game", package_id=package.package_id,
            package_version=package.package_version, expected_revision=0, observed_at=self.clock.now()).unwrap()
        repository.set_role_enabled(extension_id="game", role=self.window.role, bot_id=SCOPE.bot_id,
            enabled=True, expected_revision=0, observed_at=self.clock.now()).unwrap()
        for capability in package.capabilities:
            repository.set_authorization(extension_id="game", capability_id=capability,
                subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.ACTIVE,
                expected_revision=0, observed_at=self.clock.now()).unwrap()
        return await self.start(host)

    async def operate(self, host, action, arguments, identifier):
        async def model(envelope):
            self.assertIn("两人共享的桌边时光", envelope.original.instruction)
            self.assertIn("通过掷法、碰杯沿、手势等操作悄悄影响结果", envelope.original.instruction)
            if not envelope.tool_history:
                return requested(ToolCall(identifier, action, encode(arguments)))
            return answered("本次游戏操作已核对。")
        self.model_behavior = model
        batch = host.receive(self.event(identifier)).unwrap()
        state = await self.done(host.application, batch)
        self.assertEqual(state["state"], "complete", dict(state))
        row = self.runtime.read_one("SELECT * FROM extension_tool_invocations WHERE batch_id=?", (batch,))
        self.assertEqual(row["state"], "succeeded", dict(row))
        reference = source_from_document(json.loads(row["result_source_json"]))
        source = host.application.memory.writer.access.source(self.context(host.application, batch), reference)
        return batch, row, reference, json.loads(source.payload)["native"]["result"]["game"]

    async def experiences(self, app, context, count):
        self.advance(app, 31)
        await self.until(lambda: len(app.memory.experiences.list(context).unwrap()["items"]) == count)
        return app.memory.experiences.list(context).unwrap()["items"]

    async def test_natural_opening_background_recall_revocation_and_identity_boundary(self):
        host = await self.game_host()
        app = host.application
        self.assertIsNotNone(app.memory.game)
        with patch.object(game_provider, "fresh_shoe", return_value=shoe_with_draws(["A", "K", "9", "8"])):
            batch, row, source, game = await self.operate(host, game_provider.BLACKJACK_CREATE,
                {"difficulty": "normal"}, "natural")
        context = self.context(app, batch)
        self.assertEqual((game["status"], game["outcome"]), ("finished", "player"))
        view = (await self.experiences(app, context, 1))[0]
        self.assertIn("二十一点终局", view["title"])
        self.assertIn(game["game_id"], view["statements"][0]["text"])
        self.assertEqual(view["statements"][0]["evidence"][0]["source"]["source_id"], source.source_id)
        app.memory.query.begin(context, "game-query")
        recalled = app.memory.query.query(context, "game-query", query_intent="二十一点", kind="experiences").unwrap()
        handle = recalled["items"][0]["statements"][0]["sources"][0]
        original = app.memory.query.source(context, "game-query", handle=handle).unwrap()["text"]
        self.assertIn(game["game_id"], original)
        self.assertNotIn('"shoe"', original)
        app.memory.game.record(context, row["invocation_id"]).unwrap()
        self.assertEqual(len(app.memory.experiences.list(context).unwrap()["items"]), 1)
        self.assertFalse(app.memory.experiences.read(replace(context, actor=self.core), view["view_id"]).is_success)
        app.memory.writer.sources.revoke(source, expected_governance_revision=1,
                                         observed_at=self.clock.now()).unwrap()
        self.assertFalse(app.memory.experiences.read(context, view["view_id"]).is_success)
        self.assertFalse(app.memory.query.source(context, "game-query", handle=handle).is_success)

    async def test_active_and_closed_games_do_not_write_experiences_and_stand_does(self):
        host = await self.game_host()
        app = host.application
        with patch.object(game_provider, "fresh_shoe", return_value=shoe_with_draws(["10", "6", "9", "8", "4", "5"])):
            batch, row, _, game = await self.operate(host, game_provider.BLACKJACK_CREATE,
                {"difficulty": "normal"}, "create")
        context = self.context(app, batch)
        self.assertIsNone(app.memory.game.record(context, row["invocation_id"]).unwrap()["view_id"])
        _, _, _, closed = await self.operate(host, game_provider.BLACKJACK_CLOSE,
                                             {"game_id": game["game_id"]}, "close")
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(app.memory.game.advance(context).unwrap()["saved"], 0)
        with patch.object(game_provider, "fresh_shoe", return_value=shoe_with_draws(["10", "6", "9", "8", "5"])):
            _, _, _, game = await self.operate(host, game_provider.BLACKJACK_CREATE,
                {"difficulty": "normal"}, "create-again")
        _, _, _, game = await self.operate(host, game_provider.BLACKJACK_STAND,
                                           {"game_id": game["game_id"]}, "stand")
        self.assertEqual(game["status"], "finished")
        view = (await self.experiences(app, context, 1))[0]
        labels = {"player": "玩家获胜", "bot": "角色获胜", "draw": "平局"}
        self.assertEqual(view["title"], "二十一点终局：" + labels[game["outcome"]])

    async def test_xiangqi_terminal_receipt_survives_restart_with_same_ingestion_cursor(self):
        host = await self.game_host()
        app = host.application
        batch, _, _, game = await self.operate(host, game_provider.XIANGQI_CREATE,
            {"difficulty": "normal", "human_side": "red"}, "create")
        context = self.context(app, batch)
        _, _, source, game = await self.operate(host, game_provider.XIANGQI_MOVE,
            {"game_id": game["game_id"], "from_row": 9, "from_column": 1, "to_row": 7, "to_column": 2}, "win")
        self.assertEqual((game["status"], game["outcome"]), ("finished", "player"))
        view = (await self.experiences(app, context, 1))[0]
        self.assertIn("中国象棋终局", view["title"])
        await app.close()
        self.native_registry.close()
        await self.game_port.close()
        self.create_port()
        restarted = await self.start(self.host(runtime=self.open_runtime(), tool_port=self.native_registry,
            policy=ConversationPolicy(0, 0, 180, 0)), task_generation=1, model_generation=1)
        current = restarted.application
        self.assertEqual(current.memory.experiences.read(context, view["view_id"]).unwrap()["view_id"], view["view_id"])
        self.assertEqual(current.memory.game.advance(context).unwrap()["examined"], 0)
        self.assertTrue(current.messages.sources.validate_reference(source, observed_at=self.clock.now()).is_success)

    async def test_turtle_soup_and_draw_guess_save_only_confirmed_terminal_results(self):
        host = await self.game_host()
        app = host.application
        batch, create_row, _, turtle = await self.operate(host, game_provider.TURTLE_CREATE,
            {}, "turtle-create")
        context = self.context(app, batch)
        self.assertIsNone(app.memory.game.record(context, create_row["invocation_id"]).unwrap()["view_id"])
        scope = next(iter(self.game_port.store.data["scopes"].values()))
        puzzle = next(room["puzzle"] for room in scope.values() if room["game_id"] == turtle["game_id"])
        _, answer_row, turtle_source, turtle = await self.operate(host, game_provider.TURTLE_ANSWER,
            {"game_id": turtle["game_id"], "answer": puzzle["solution"], "solved": True,
             "matched_facts": list(range(len(puzzle["key_facts"])))}, "turtle-solved")
        self.assertEqual((turtle["status"], turtle["outcome"]), ("finished", "player"))
        turtle_view = (await self.experiences(app, context, 1))[0]
        self.assertEqual(turtle_view["title"], "海龟汤终局：玩家解开汤底")
        self.assertTrue(app.memory.game.record(context, answer_row["invocation_id"]).is_success)
        self.assertEqual(len(app.memory.experiences.list(context).unwrap()["items"]), 1)

        _, draw_create_row, _, draw = await self.operate(host, game_provider.DRAW_CREATE,
            {"difficulty": "easy"}, "draw-create")
        self.assertIsNone(app.memory.game.record(context, draw_create_row["invocation_id"]).unwrap()["view_id"])
        room = next(room for room in self.game_port.store.data["scopes"][
            next(iter(self.game_port.store.data["scopes"]))].values() if room["game_id"] == draw["game_id"])
        _, guess_row, draw_source, draw = await self.operate(host, game_provider.DRAW_GUESS,
            {"game_id": draw["game_id"], "guess": room["target"]["answer"]}, "draw-guessed")
        self.assertEqual((draw["status"], draw["outcome"]), ("finished", "player"))
        draw_views = await self.experiences(app, context, 2)
        self.assertIn("你画我猜终局：合作猜中", {item["title"] for item in draw_views})
        self.assertTrue(app.memory.game.record(context, guess_row["invocation_id"]).is_success)
        self.assertEqual(len(app.memory.experiences.list(context).unwrap()["items"]), 2)
        self.assertTrue(turtle_source.source_id)
        self.assertTrue(draw_source.source_id)


if __name__ == "__main__":
    unittest.main()
