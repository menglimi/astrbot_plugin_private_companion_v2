"""A real web result is available to the next authorized core chat turn."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from tests import astrbot_data_root as _host_import_root
from astrbot.core.provider.entities import ProviderRequest
from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from astrbot_host.native_extensions.game.host_events import GameHostEvents
from companion_v2.execution.models import TaskContext, encode
from companion_v2.foundation.refs import AudienceRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.games.native import provider as games
from companion_v2.games.native.context import GAME_LABELS, conversation_records
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, ResolvedIdentity, RoleBinding
from companion_v2.product import PRODUCT_VERSION
from tests.test_game_native_web import request
from tests.test_game_native_xiangqi import FakeEngine
from tests.test_native_host_events import HostEvent, context_text


def chat_context(*, user="200", role="xingyuan", conversation="current", bot="bot-a"):
    scope = ScopeRef("game-fixture", "onebot", ScopeKind.PRIVATE, user, bot, "account-a", conversation, user)
    actor = ResolvedIdentity(AuthenticatedHostPrincipal("game-fixture", "astrbot", "onebot", user,
                            bot, "account-a"), SubjectRef("game-fixture", SubjectKind.HUMAN, user), "binding-" + user, 1, 1)
    return TaskContext(actor, RoleBinding(scope, SubjectRef("game-fixture", SubjectKind.BOT, role), 1),
                       AudienceRef(scope, (actor.subject,)))


class NativeGameContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.runtime = NS(**{f"native_v2_{kind}_enabled": True for kind in GAME_LABELS},
                          xiangqi_engine=FakeEngine(), private_qq_game_context_enabled=True,
                          recent_game_result_ttl_seconds=1800, manager=NS(for_session=lambda _: []),
                          _recent_private_game_results={})
        self.context = chat_context()
        self.available = {f"game.{kind}.snapshot" for kind in GAME_LABELS}
        self.catalog = Mock(side_effect=lambda _: [NS(action=action) for action in self.available])
        self.runtime.controller = NS(session=NS(application=NS(tools=NS(external=NS(catalog_for=self.catalog)))))
        self.provider = self.reopen()
        self.current = True
        self.owner = GameHostEvents(self.runtime, lambda: self.current)

    def reopen(self):
        provider = games.NativeGameProvider(self.runtime, self.root, version=PRODUCT_VERSION)
        self.runtime._native_provider = provider
        return provider

    async def execute(self, action, args, identifier, context=None):
        value = request(self.provider, action, args, identifier)
        value["context"] = json.loads(encode(context or self.context))
        return await self.provider.execute(value, before_dispatch=lambda: True)

    def snapshot(self, *, context=None, now=None, ttl=1800):
        return self.provider.conversation_snapshot(json.loads(encode(context or self.context)),
            authorized_actions=self.available, now=now or time.time(), result_ttl=ttl, before_read=lambda: True)

    def prompt(self, *, event=None, context=None):
        event = event or HostEvent(text="呜")
        event.extra[CORE_REPLY_CONTEXT_EXTRA] = {"prepared": {"context": context or self.context}}
        req = ProviderRequest(system_prompt="星缘的原人格", prompt=event.message_str)
        self.owner.request(event, req)
        return req

    async def finished_gomoku(self):
        created = await self.execute(games.GOMOKU_CREATE, {"difficulty": "normal", "human_side": "white"}, "start")
        game_id = created["result"]["game"]["game_id"]
        ticket = self.provider.issue_web_ticket(game_id)
        for column in range(8, 12):
            result = await self.provider.web_action(ticket, {"action": "interact", "source": {"kind": "tray", "color": 1},
                "target": {"row": 7, "column": column, "x": .5, "y": .5}, "interaction": "click"})
        self.assertEqual(result["game"]["status"], "finished")
        self.assertEqual(result["game"]["outcome"], "bot")
        return game_id

    async def test_web_finish_enters_natural_core_turn_and_survives_reload_without_writes(self):
        game_id = await self.finished_gomoku()
        self.provider = self.reopen()
        before = self.provider.store.path.read_bytes()
        req = self.prompt()
        self.assertEqual(req.prompt, "呜")
        self.assertEqual(req.system_prompt, "星缘的原人格")
        self.assertIn(game_id, context_text(req))
        self.assertIn("当前角色获胜、当前用户落败", context_text(req))
        self.assertIn('"user_side":"白棋"', context_text(req))
        self.assertIn('"role_side":"黑棋"', context_text(req))
        self.assertIn('"status":"finished"', context_text(req))
        self.assertEqual(before, self.provider.store.path.read_bytes())
        self.catalog.assert_called_once_with(self.context)

    async def test_context_tracks_live_moves_and_checks_scope_and_revoked_read_grant(self):
        opened = await self.execute(games.GOMOKU_CREATE, {"difficulty": "normal", "human_side": "white"}, "open")
        game_id = opened["result"]["game"]["game_id"]
        ticket = self.provider.issue_web_ticket(game_id)
        self.assertEqual(self.snapshot()[0]["move_count"], 1)
        await self.provider.web_action(ticket, {"action": "move", "row": 7, "column": 8})
        self.assertEqual(self.snapshot()[0]["move_count"], 3)
        for context in (chat_context(user="300"), chat_context(role="other-role"),
                        chat_context(conversation="other-conversation"), chat_context(bot="other-bot")):
            with self.subTest(context=context.key):
                self.assertEqual(self.snapshot(context=context), [])
        rebound = replace(self.context, actor=replace(self.context.actor, policy_revision=2))
        self.assertEqual(self.snapshot(context=rebound)[0]["game_id"], game_id)
        self.available.clear()
        req = self.prompt()
        self.assertEqual(req.system_prompt, "星缘的原人格")
        self.assertFalse(req.extra_user_content_parts)
        self.available.add(games.GOMOKU_MOVE)  # Move permission alone cannot grant a context read.
        self.assertFalse(self.prompt().extra_user_content_parts)
        self.available.add(games.GOMOKU_READ)
        req = self.prompt()
        self.assertIn(game_id, context_text(req))
        self.assertIn('"move_count":3', context_text(req))
        event = HostEvent()
        event.extra[CORE_REPLY_CONTEXT_EXTRA] = {"prepared": {"context": self.context}}
        self.available.clear()
        self.owner.request(event, req)
        self.assertFalse(req.extra_user_content_parts)
        self.available.add(games.GOMOKU_READ)
        self.owner.request(event, req)
        self.assertIn(game_id, context_text(req))
        self.current = False
        self.owner.request(event, req)
        self.assertFalse(req.extra_user_content_parts)
        self.assertEqual(req.system_prompt, "星缘的原人格")

    async def test_all_seven_game_types_use_public_context_without_hidden_material_or_engine_io(self):
        actions = {"tictactoe": games.CREATE, "gomoku": games.GOMOKU_CREATE, "pig_dice": games.PIG_CREATE,
                   "blackjack": games.BLACKJACK_CREATE, "xiangqi": games.XIANGQI_CREATE,
                   "turtle_soup": games.TURTLE_CREATE, "draw_guess": games.DRAW_CREATE}
        for kind, action in actions.items():
            args = {} if kind == "turtle_soup" else {"difficulty": "normal"}
            if kind == "xiangqi":
                args["human_side"] = "red"
            await self.execute(action, args, "create-" + kind)
        engine_calls = len(self.runtime.xiangqi_engine.calls)
        facts = self.snapshot()
        self.assertEqual({fact["game_type"] for fact in facts}, set(GAME_LABELS))
        self.assertEqual(len(self.runtime.xiangqi_engine.calls), engine_calls)
        text = encode(facts)
        for forbidden in ('"solution"', '"key_facts"', '"target"', '"answer"', '"shoe"', '"dealer_cards"'):
            self.assertNotIn(forbidden, text)
        for kind, action in (("turtle_soup", games.TURTLE_GIVE_UP), ("draw_guess", games.DRAW_GIVE_UP)):
            game_id = next(fact["game_id"] for fact in facts if fact["game_type"] == kind)
            await self.execute(action, {"game_id": game_id}, "give-up-" + kind)
        ended = {fact["game_type"]: fact for fact in self.snapshot()}
        for kind in ("turtle_soup", "draw_guess"):
            self.assertEqual(ended[kind]["status"], "finished")
            self.assertIn("未解答成功", ended[kind]["result"])
        self.assertNotIn('"solution"', encode(ended))
        self.assertNotIn('"answer"', encode(ended))

    async def test_real_finish_ttl_does_not_advance_on_reads_or_replay(self):
        game_id = await self.finished_gomoku()
        ended = self.snapshot()[0]["ended_at"]
        self.assertEqual(self.snapshot(now=ended + 1799)[0]["game_id"], game_id)
        self.assertEqual(self.snapshot(now=ended + 1801), [])
        self.assertEqual(self.snapshot(ttl=0), [])
        before = self.provider.store.path.read_bytes()
        await self.execute(games.GOMOKU_READ, {}, "read")
        self.assertEqual(before, self.provider.store.path.read_bytes())
        await self.execute(games.GOMOKU_CLOSE, {"game_id": game_id}, "close-finished")
        stamp = self.snapshot()[0]["ended_at"]
        await self.execute(games.GOMOKU_CLOSE, {"game_id": game_id}, "close-finished")
        self.assertEqual(stamp, ended)
        self.assertEqual(self.snapshot()[0]["ended_at"], ended)

    def test_recent_finish_selection_does_not_let_an_old_closed_room_replace_result(self):
        rooms = {"game-f-old": {"game_id": "game-f-old", "game_type": "gomoku", "status": "closed"},
                 "game-4-new": {"game_id": "game-4-new", "game_type": "gomoku", "status": "finished"}}
        selected = conversation_records(rooms, {"gomoku"}, now=10000, result_ttl=1800)
        self.assertEqual([item["game_id"] for item in selected], ["game-4-new"])
        rooms["game-4-new"].update(ended_at=9995, updated_at=9995)
        rooms["game-a-active"] = {"game_id": "game-a-active", "game_type": "gomoku", "status": "active", "updated_at": 9996}
        selected = conversation_records(rooms, {"gomoku"}, now=10000, result_ttl=1800)
        self.assertEqual([item["game_id"] for item in selected], ["game-4-new", "game-a-active"])
        self.assertEqual([item["game_id"] for item in conversation_records(rooms, {"gomoku"}, now=12000, result_ttl=1800)], ["game-a-active"])

    async def test_group_or_another_sender_cannot_receive_private_game_facts(self):
        await self.finished_gomoku()
        for event in (HostEvent(sender="300"), HostEvent(private=False)):
            req = self.prompt(event=event)
            self.assertEqual(req.system_prompt, "星缘的原人格")
            self.assertFalse(req.extra_user_content_parts)


if __name__ == "__main__":
    unittest.main()
