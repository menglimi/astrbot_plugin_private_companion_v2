"""Core Game tools feed terminal receipts to the private experience producer."""

from dataclasses import replace
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as host_support
from astrbot.core.agent.message import Message, ToolCall as NativeCall
from astrbot_host.core_reply import prepare_core_reply_event
from astrbot_host.core_reply_observations import CoreReplyObservations
from astrbot_host.core_reply_tools import close_core_reply_tools, inject_core_reply_tools, native_tool_name
from companion_v2.adapters.astrbot.native import NativeConversationInput
from companion_v2.games.native import provider as game_provider
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.messages import source_from_document
from companion_v2.execution.models import TaskContext, digest, encode, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.product import PRODUCT_VERSION
from tests.native_internal_support import internal_registry
from tests.test_game_native_blackjack import shoe_with_draws
from tests.test_game_native_xiangqi import FakeEngine
from tests.test_host_application import HostFixture
from tests.test_management_access import SCOPE
from tests.test_astrbot_core_reply import FakeEvent


class GameMemoryTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_core_tool_terminal_receipt_reaches_background_experience_without_reply_batch(self):
        from astrbot.core.agent.message import Message, ToolCall as NativeCall
        from astrbot_host.core_reply import prepare_core_reply_event
        from astrbot_host.core_reply_tools import close_core_reply_tools, inject_core_reply_tools, native_tool_name
        from companion_v2.execution.models import TaskContext, require
        from companion_v2.foundation.refs import AudienceRef
        from tests.test_astrbot_core_reply import FakeEvent

        host = await self.game_host()
        app = host.application
        self.addAsyncCleanup(close_core_reply_tools, app)
        context = TaskContext(self.important, require(self.identity.resolve_role(SCOPE, observed_at=self.clock.now())),
                              AudienceRef(SCOPE, (self.important.subject,)))
        event = FakeEvent()
        prepare_core_reply_event(event, {"context": context, "event_id": "native-game"},
                                 authorize=lambda _: asyncio.sleep(0, result=Outcome.success(True)))
        request = SimpleNamespace(func_tool=None, system_prompt="原人格")
        inject_core_reply_tools(event, request, application=app)
        name = native_tool_name(game_provider.BLACKJACK_CREATE)
        call = NativeCall(id="native-natural", function=NativeCall.FunctionBody(name=name, arguments='{"difficulty":"normal"}'))
        wrapper = SimpleNamespace(context=SimpleNamespace(event=event), messages=[Message(role="assistant", tool_calls=[call])])
        with patch.object(game_provider, "fresh_shoe", return_value=shoe_with_draws(["A", "K", "9", "8"])):
            result = json.loads(await request.func_tool.get_tool(name).call(wrapper, difficulty="normal"))
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(app.memory.game.advance(context).unwrap()["saved"], 1)
        self.assertEqual(app.memory.game.advance(context).unwrap()["saved"], 0)
        view = app.memory.experiences.list(context).unwrap()["items"][0]
        self.assertIn("二十一点终局：玩家获胜", view["title"])
        self.assertEqual(self.runtime.read_all("SELECT * FROM conversation_batches", ()), ())
        self.assertEqual(self.called, [])
        self.assertEqual(event.sent, [])

    def create_port(self):
        plugin = SimpleNamespace(native_v2_blackjack_enabled=True, native_v2_xiangqi_enabled=True,
            native_v2_turtle_soup_enabled=True, native_v2_turtle_soup_content_level="all_ages",
            native_v2_turtle_soup_max_hints=3, native_v2_draw_guess_enabled=True,
            native_v2_draw_guess_max_guesses=5, native_v2_draw_guess_duration_seconds=120,
            xiangqi_engine=FakeEngine())
        self.game_port = game_provider.NativeGameProvider(plugin, self.root.parent / "game-provider", version=PRODUCT_VERSION)
        self.addAsyncCleanup(self.game_port.close)
        self.native_registry = internal_registry(self.game_port, now=self.clock.now)
        self.addAsyncCleanup(self.native_registry.aclose)

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
        started = await self.start(host)
        self.addAsyncCleanup(close_core_reply_tools, started.application)
        return started

    async def operate(self, host, action, arguments, identifier):
        app = host.application
        context = TaskContext(self.important, require(self.identity.resolve_role(SCOPE, observed_at=self.clock.now())),
                              AudienceRef(SCOPE, (self.important.subject,)))

        def check_context(current):
            return app.tasks.check_context_access(current, action="conversation.reply", observed_at=self.clock.now())

        observer = CoreReplyObservations(SimpleNamespace(application=app, runtime=app.runtime,
            now=self.clock.now, authorize=lambda current: require(check_context(current))))
        self.addAsyncCleanup(observer.close)
        native_input = NativeConversationInput(identifier, context.actor.principal,
            ConversationRoute(SCOPE, user=context.actor.subject), context.audience,
            "本次游戏操作 " + identifier, self.clock.now(), context.role_binding.role, "原角色人格提示")
        turn = "core-reply:" + digest([context.key, identifier])
        pending = observer.input(context, native_input, turn_id=turn)
        self.assertIsNotNone(await pending)
        await app.state_maintenance.bind_async(context, native_input.instruction)
        prepared = {"context": context, "event_id": identifier, "turn_id": turn,
            "instruction": native_input.instruction, "native_input": native_input, "native_source_future": pending}
        event = FakeEvent()
        prepare_core_reply_event(event, prepared,
            authorize=lambda _: asyncio.sleep(0, result=check_context(context)))
        request = SimpleNamespace(func_tool=None, system_prompt=native_input.instruction)
        offered = inject_core_reply_tools(event, request, application=app)
        self.assertEqual({item for item in offered if item.startswith("game.")},
                         set(self.game_port.manifest()["package"]["capabilities"]))
        name = native_tool_name(action)
        call = NativeCall(id=identifier, function=NativeCall.FunctionBody(name=name, arguments=encode(arguments)))
        wrapper = SimpleNamespace(context=SimpleNamespace(event=event), messages=[Message(role="assistant", tool_calls=[call])])
        await observer.phase(prepared, "running")
        result = json.loads(await request.func_tool.get_tool(name).call(wrapper, **arguments))
        self.assertEqual(result["state"], "succeeded", result)
        await observer.phase(prepared, "completed")
        row = app.tools.external._row(result["invocation_id"])
        self.assertEqual(row["state"], "succeeded", dict(row))
        self.assertEqual(row["execution_path"], "astrbot_core")
        reference = source_from_document(json.loads(row["result_source_json"]))
        source = app.memory.writer.access.source(context, reference)
        self.assertEqual(app.runtime.read_all("SELECT * FROM conversation_batches", ()), ())
        self.assertEqual(self.called, [])
        self.assertEqual(self.sent, [])
        self.assertEqual(event.sent, [])
        return context, row, reference, json.loads(source.payload)["native"]["result"]["game"]

    async def experiences(self, app, context, count):
        self.advance(app, 31)
        await self.until(lambda: len(app.memory.experiences.list(context).unwrap()["items"]) == count)
        return app.memory.experiences.list(context).unwrap()["items"]

    async def test_natural_opening_background_recall_revocation_and_identity_boundary(self):
        host = await self.game_host()
        app = host.application
        self.assertIsNotNone(app.memory.game)
        with patch.object(game_provider, "fresh_shoe", return_value=shoe_with_draws(["A", "K", "9", "8"])):
            context, row, source, game = await self.operate(host, game_provider.BLACKJACK_CREATE,
                {"difficulty": "normal"}, "natural")
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
            context, row, _, game = await self.operate(host, game_provider.BLACKJACK_CREATE,
                {"difficulty": "normal"}, "create")
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
        context, _, _, game = await self.operate(host, game_provider.XIANGQI_CREATE,
            {"difficulty": "normal", "human_side": "red"}, "create")
        _, _, source, game = await self.operate(host, game_provider.XIANGQI_MOVE,
            {"game_id": game["game_id"], "from_row": 9, "from_column": 1, "to_row": 7, "to_column": 2}, "win")
        self.assertEqual((game["status"], game["outcome"]), ("finished", "player"))
        view = (await self.experiences(app, context, 1))[0]
        self.assertIn("中国象棋终局", view["title"])
        await app.close()
        await self.native_registry.aclose()
        await self.game_port.close()
        self.create_port()
        restarted = await self.start(self.host(runtime=self.open_runtime(), tool_port=self.native_registry,
            policy=ConversationPolicy(0, 0, 180, 0)), task_generation=1, model_generation=1)
        current = restarted.application
        self.addAsyncCleanup(close_core_reply_tools, current)
        self.assertEqual(current.memory.experiences.read(context, view["view_id"]).unwrap()["view_id"], view["view_id"])
        self.assertEqual(current.memory.game.advance(context).unwrap()["examined"], 0)
        self.assertTrue(current.messages.sources.validate_reference(source, observed_at=self.clock.now()).is_success)

    async def test_turtle_soup_and_draw_guess_save_only_confirmed_terminal_results(self):
        host = await self.game_host()
        app = host.application
        context, create_row, _, turtle = await self.operate(host, game_provider.TURTLE_CREATE,
            {}, "turtle-create")
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
