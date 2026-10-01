from __future__ import annotations

import pytest

from companion_v2.games import BLACK, EMPTY, WHITE, GomokuGame


def test_freestyle_five_or_more_wins() -> None:
    game = GomokuGame(human_color=BLACK)
    for column in range(4):
        game.board[7][column] = BLACK
        game.history.append((7, column, BLACK))

    game.place(7, 4, BLACK)

    assert game.winner == BLACK
    assert game.finished


def test_move_rejects_wrong_turn_and_occupied_cell() -> None:
    game = GomokuGame(human_color=BLACK)
    with pytest.raises(ValueError, match="轮到"):
        game.place(7, 7, WHITE)
    game.place(7, 7, BLACK)
    with pytest.raises(ValueError, match="有棋子"):
        game.place(7, 7, WHITE)


@pytest.mark.parametrize("difficulty", ["normal", "hard"])
def test_bot_blocks_an_immediate_human_win(difficulty: str) -> None:
    game = GomokuGame(human_color=BLACK, difficulty=difficulty)
    for column in range(4, 8):
        game.board[8][column] = BLACK
        game.history.append((8, column, BLACK))
    game.turn = WHITE

    row, column = game.choose_bot_move(seed=2, time_limit=0.1)

    assert row == 8
    assert column in {3, 8}


def test_bot_takes_an_immediate_win_before_blocking() -> None:
    game = GomokuGame(human_color=BLACK, difficulty="normal")
    for column in range(4):
        game.board[6][column] = WHITE
        game.history.append((6, column, WHITE))
        game.board[9][column] = BLACK
        game.history.append((9, column, BLACK))
    game.turn = WHITE

    assert game.choose_bot_move(seed=1) == (6, 4)


def test_undo_removes_player_and_following_bot_stone() -> None:
    game = GomokuGame(human_color=BLACK)
    game.place(7, 7, BLACK)
    game.place(7, 8, WHITE)
    game.place(6, 7, BLACK)
    game.place(6, 8, WHITE)

    assert game.undo_round() == 2
    assert game.board[6][7] == EMPTY
    assert game.board[6][8] == EMPTY
    assert game.turn == BLACK


def test_move_threat_reports_distinct_winning_points() -> None:
    game = GomokuGame(human_color=BLACK)
    for column in range(4, 8):
        game.board[7][column] = BLACK

    threat = game.move_threat(7, 7, BLACK)

    assert threat.kind == "multiple"
    assert threat.winning_points == ((7, 3), (7, 8))


def test_move_threat_respects_blockers_and_internal_gaps() -> None:
    blocked = GomokuGame(human_color=BLACK)
    blocked.board[7][3] = WHITE
    for column in range(4, 8):
        blocked.board[7][column] = BLACK
    assert blocked.move_threat(7, 7, BLACK).winning_points == ((7, 8),)

    gap = GomokuGame(human_color=BLACK)
    for column in (4, 5, 7, 8):
        gap.board[7][column] = BLACK
    assert gap.move_threat(7, 8, BLACK).winning_points == ((7, 6),)


def test_snapshot_excludes_move_history() -> None:
    snapshot = GomokuGame().snapshot()

    assert snapshot["move_count"] == 0
    assert "history" not in snapshot
