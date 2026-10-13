"""Scope, hidden answers, replay and terminal receipts for native chat games."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_v2.games.native import provider as game_provider
from companion_v2.product import PRODUCT_VERSION
from tests.test_game_native_pig_dice import request


def enabled_plugin(**changes):
    defaults = {
        "native_v2_turtle_soup_enabled": True,
        "native_v2_turtle_soup_content_level": "all_ages",
        "native_v2_turtle_soup_max_hints": 2,
        "native_v2_draw_guess_enabled": True,
        "native_v2_draw_guess_max_guesses": 2,
        "native_v2_draw_guess_duration_seconds": 120,
    }
    defaults.update(changes)
    return SimpleNamespace(**defaults)


class NativeTurtleSoupTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_judge_context_public_snapshot_and_terminal_replay(self):
        with tempfile.TemporaryDirectory() as root:
            plugin = enabled_plugin()
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            manifest = provider.manifest()
            self.assertEqual(len(manifest["tools"]), 35)
            self.assertEqual({tool["action"] for tool in manifest["tools"]
                              if tool["action"].startswith(("game.turtle_soup.", "game.draw_guess."))},
                game_provider.TURTLE_ACTIONS | game_provider.DRAW_ACTIONS)

            opened = await provider.execute(request(provider, game_provider.TURTLE_CREATE,
                {}, "turtle-create"), before_dispatch=lambda: True)
            game = opened["result"]["game"]
            game_id = game["game_id"]
            public = json.dumps(game, ensure_ascii=False)
            self.assertNotIn("solution", public)
            self.assertNotIn("key_facts", public)
            self.assertNotIn("judge_context", public)

            private = await provider.execute(request(provider, game_provider.TURTLE_PRIVATE_CONTEXT,
                {}, "turtle-private"), before_dispatch=lambda: True)
            puzzle = private["result"]["judge_context"]["puzzle"]
            self.assertIn(puzzle["solution"], json.dumps(private["result"], ensure_ascii=False))
            other = await provider.execute(request(provider, game_provider.TURTLE_PRIVATE_CONTEXT,
                {}, "turtle-other", subject="player-b"), before_dispatch=lambda: True)
            self.assertIsNone(other["result"]["judge_context"])

            question = request(provider, game_provider.TURTLE_ASK, {"game_id": game_id,
                "question": "这件事和约定有关吗？", "verdict": "yes", "matched_facts": [0]},
                "turtle-question")
            answered = await provider.execute(question, before_dispatch=lambda: True)
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            replayed = await provider.execute(question, before_dispatch=lambda: True)
            self.assertEqual(replayed, answered)
            self.assertEqual(len(next(iter(next(iter(provider.store.data["scopes"].values())).values()))["events"]), 1)

            solved = request(provider, game_provider.TURTLE_ANSWER, {"game_id": game_id,
                "answer": puzzle["solution"], "solved": True,
                "matched_facts": list(range(len(puzzle["key_facts"])))}, "turtle-solved")
            result = await provider.execute(solved, before_dispatch=lambda: True)
            finished = result["result"]["game"]
            self.assertEqual((finished["status"], finished["outcome"]), ("finished", "player"))
            self.assertEqual(finished["state"]["puzzle"]["solution"], puzzle["solution"])
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            self.assertEqual(await provider.execute(solved, before_dispatch=lambda: True), result)

    async def test_invalid_facts_close_and_disabled_provider(self):
        with tempfile.TemporaryDirectory() as root:
            plugin = enabled_plugin()
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            game = (await provider.execute(request(provider, game_provider.TURTLE_CREATE,
                {}, "create"), before_dispatch=lambda: True))["result"]["game"]
            invalid = request(provider, game_provider.TURTLE_ASK, {"game_id": game["game_id"],
                "question": "问题", "verdict": "yes", "matched_facts": [7]}, "invalid")
            rejected = await provider.execute(invalid, before_dispatch=lambda: True)
            self.assertEqual((rejected["state"], rejected["effect"]), ("failed", "not_committed"))
            room = next(iter(next(iter(provider.store.data["scopes"].values())).values()))
            self.assertEqual(room["events"], [])
            closed = await provider.execute(request(provider, game_provider.TURTLE_CLOSE,
                {"game_id": game["game_id"]}, "close"), before_dispatch=lambda: True)
            self.assertEqual(closed["result"]["game"]["status"], "closed")
            self.assertNotIn("solution", json.dumps(closed["result"]["game"], ensure_ascii=False))
            plugin.native_v2_turtle_soup_enabled = False
            with self.assertRaisesRegex(game_provider.NativeGameError, "game_turtle_soup_disabled"):
                await provider.execute(request(provider, game_provider.TURTLE_READ, {}, "disabled"),
                                       before_dispatch=lambda: True)


class NativeDrawGuessTests(unittest.IsolatedAsyncioTestCase):
    async def test_answer_stays_hidden_until_authoritative_guess_and_replay(self):
        with tempfile.TemporaryDirectory() as root:
            plugin = enabled_plugin()
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            with patch.object(game_provider.random, "choice", return_value=game_provider.DrawWord(
                    "苹果", ("apple",))):
                opened = await provider.execute(request(provider, game_provider.DRAW_CREATE,
                    {"difficulty": "easy"}, "draw-create"), before_dispatch=lambda: True)
            game = opened["result"]["game"]
            game_id = game["game_id"]
            self.assertNotIn("苹果", json.dumps(game, ensure_ascii=False))
            self.assertNotIn("answer", game["state"])

            wrong = await provider.execute(request(provider, game_provider.DRAW_GUESS,
                {"game_id": game_id, "guess": "香蕉"}, "draw-wrong"), before_dispatch=lambda: True)
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            repeat = await provider.execute(request(provider, game_provider.DRAW_GUESS,
                {"game_id": game_id, "guess": "香蕉"}, "draw-wrong"), before_dispatch=lambda: True)
            self.assertEqual(repeat, wrong)
            self.assertEqual(len(next(iter(next(iter(provider.store.data["scopes"].values())).values()))["guesses"]), 1)

            correct = await provider.execute(request(provider, game_provider.DRAW_GUESS,
                {"game_id": game_id, "guess": "apple"}, "draw-correct"), before_dispatch=lambda: True)
            finished = correct["result"]["game"]
            self.assertEqual((finished["status"], finished["outcome"]), ("finished", "player"))
            self.assertEqual(finished["state"]["answer"], "苹果")
            other = await provider.execute(request(provider, game_provider.DRAW_READ, {}, "draw-other",
                subject="player-b"), before_dispatch=lambda: True)
            self.assertIsNone(other["result"]["game"])

    async def test_guess_limit_timeout_and_give_up(self):
        with tempfile.TemporaryDirectory() as root:
            plugin = enabled_plugin(native_v2_draw_guess_max_guesses=1)
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            with patch.object(game_provider.random, "choice", return_value=game_provider.DrawWord("猫")), \
                    patch.object(game_provider.time, "time", return_value=1000):
                opened = await provider.execute(request(provider, game_provider.DRAW_CREATE,
                    {"difficulty": "easy"}, "draw-create"), before_dispatch=lambda: True)
            game_id = opened["result"]["game"]["game_id"]
            lost = await provider.execute(request(provider, game_provider.DRAW_GUESS,
                {"game_id": game_id, "guess": "狗"}, "draw-last"), before_dispatch=lambda: True)
            self.assertEqual((lost["result"]["game"]["status"], lost["result"]["game"]["outcome"]),
                             ("finished", "bot"))

            with patch.object(game_provider.random, "choice", return_value=game_provider.DrawWord("太阳")), \
                    patch.object(game_provider.time, "time", return_value=1000):
                opened = await provider.execute(request(provider, game_provider.DRAW_CREATE,
                    {"difficulty": "easy"}, "draw-timeout-create"), before_dispatch=lambda: True)
            game_id = opened["result"]["game"]["game_id"]
            with patch.object(game_provider.time, "time", return_value=1120):
                expired = await provider.execute(request(provider, game_provider.DRAW_GUESS,
                    {"game_id": game_id, "guess": "太阳"}, "draw-expired"), before_dispatch=lambda: True)
            self.assertEqual((expired["result"]["game"]["status"], expired["result"]["game"]["outcome"]),
                             ("finished", "bot"))
            self.assertTrue(expired["result"]["game"]["state"]["timed_out"])


if __name__ == "__main__":
    unittest.main()
