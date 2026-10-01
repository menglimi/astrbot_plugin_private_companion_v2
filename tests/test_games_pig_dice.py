from __future__ import annotations

import pytest

from companion_v2.games import PigDiceGame


def test_roll_accumulates_until_player_holds() -> None:
    game = PigDiceGame(turn="human")

    assert game.roll("human", value=4) == 4
    assert game.roll("human", value=6) == 6
    assert game.turn_total == 10
    assert game.hold("human") == 10
    assert game.human_score == 10
    assert game.turn == "bot"
    assert game.turn_total == 0


def test_rolling_one_loses_only_unbanked_score() -> None:
    game = PigDiceGame(turn="human", human_score=12)
    game.roll("human", value=5)

    game.roll("human", value=1)

    assert game.human_score == 12
    assert game.turn_total == 0
    assert game.turn == "bot"
    assert game.history[-1]["lost"] == 5


def test_holding_at_target_finishes_the_game() -> None:
    game = PigDiceGame(turn="human", human_score=46)
    game.roll("human", value=4)

    game.hold("human")

    assert game.finished
    assert game.winner == "human"
    assert game.human_score == 50


def test_bot_threshold_tracks_difficulty_and_score_pressure() -> None:
    cautious = PigDiceGame(difficulty="easy", turn="bot")
    balanced = PigDiceGame(difficulty="normal", turn="bot")
    bold = PigDiceGame(difficulty="hard", turn="bot")
    assert cautious.bot_hold_threshold() < balanced.bot_hold_threshold()
    assert balanced.bot_hold_threshold() < bold.bot_hold_threshold()

    balanced.human_score = 35
    balanced.bot_score = 15
    assert balanced.bot_hold_threshold() > 15
    balanced.human_score = 10
    balanced.bot_score = 35
    assert balanced.bot_hold_threshold() < 15


def test_bot_holds_if_banking_wins() -> None:
    game = PigDiceGame(difficulty="hard", turn="bot", bot_score=47)
    game.roll("bot", value=3)

    assert game.bot_should_hold()


def test_wrong_actor_and_empty_hold_are_rejected() -> None:
    game = PigDiceGame(turn="human")
    with pytest.raises(ValueError, match="轮到"):
        game.roll("bot", value=3)
    with pytest.raises(ValueError, match="可以存下"):
        game.hold("human")
