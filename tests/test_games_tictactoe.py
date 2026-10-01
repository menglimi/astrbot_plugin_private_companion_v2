from __future__ import annotations

import copy

import pytest

from companion_v2.games import EMPTY, NOUGHT, X, TicTacToeGame


def test_tictactoe_enforces_turns_and_detects_winner() -> None:
    game = TicTacToeGame(human_mark=X)
    for row, column, mark in (
        (0, 0, X),
        (1, 0, NOUGHT),
        (0, 1, X),
        (1, 1, NOUGHT),
        (0, 2, X),
    ):
        game.place(row, column, mark)

    assert game.finished
    assert game.winner == X
    assert not game.draw
    with pytest.raises(ValueError, match="结束"):
        game.place(2, 2, NOUGHT)


def test_normal_bot_takes_a_win_and_blocks_a_loss() -> None:
    winning = TicTacToeGame(human_mark=NOUGHT, difficulty="normal")
    winning.board = [[X, X, EMPTY], [NOUGHT, NOUGHT, EMPTY], [EMPTY] * 3]
    winning.turn = X
    winning.history = [(0, 0, X), (1, 0, NOUGHT), (0, 1, X), (1, 1, NOUGHT)]
    assert winning.choose_bot_move(seed=1) == (0, 2)

    blocking = TicTacToeGame(human_mark=X, difficulty="normal")
    blocking.board = [[X, X, EMPTY], [NOUGHT, EMPTY, EMPTY], [EMPTY] * 3]
    blocking.turn = NOUGHT
    blocking.history = [(0, 0, X), (1, 0, NOUGHT), (0, 1, X)]
    assert blocking.choose_bot_move(seed=1) == (0, 2)


@pytest.mark.parametrize("human_mark", [X, NOUGHT])
def test_hard_bot_cannot_be_forced_to_lose(human_mark: int) -> None:
    def explore(game: TicTacToeGame) -> None:
        assert game.winner != game.human_mark
        if game.finished:
            return
        if game.turn == game.bot_mark:
            next_game = copy.deepcopy(game)
            row, column = next_game.choose_bot_move(seed=7)
            next_game.place(row, column, next_game.bot_mark)
            explore(next_game)
            return
        for row, column in game._legal_moves():
            next_game = copy.deepcopy(game)
            next_game.place(row, column, next_game.human_mark)
            explore(next_game)

    explore(TicTacToeGame(human_mark=human_mark, difficulty="hard"))


def test_undo_removes_the_latest_human_round() -> None:
    game = TicTacToeGame(human_mark=X)
    game.place(0, 0, X)
    game.place(1, 1, NOUGHT)
    game.place(0, 1, X)
    game.place(0, 2, NOUGHT)

    assert game.undo_round() == 2
    assert game.history == [(0, 0, X), (1, 1, NOUGHT)]
    assert game.turn == X
