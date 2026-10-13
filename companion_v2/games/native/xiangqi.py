"""Rebuild and present an engine-validated V2 Xiangqi ledger."""

from __future__ import annotations

from typing import Any

from ..xiangqi import XiangqiGame


MAX_MOVES = 512


def outcome(game: XiangqiGame) -> str | None:
    if game.draw:
        return "draw"
    if game.winner is not None:
        return "player" if game.winner == game.human_side else "bot"
    return None


async def replay(engine: Any, record: dict[str, Any]) -> XiangqiGame:
    game = await XiangqiGame.create(engine, human_side=record["human_side"],
                                    difficulty=record["difficulty"])
    if not game.legal_moves:
        raise RuntimeError("xiangqi engine returned no initial legal moves")
    for move in record["moves"]:
        if game.finished or move not in game.legal_moves:
            raise ValueError("invalid xiangqi ledger move")
        await game._apply(engine, move)
    actual = outcome(game)
    if (record["status"] == "finished") != game.finished or record["outcome"] != actual:
        raise ValueError("invalid xiangqi ledger result")
    if record["status"] == "active" and game.turn != game.human_side:
        raise ValueError("invalid xiangqi ledger turn")
    return game


def view(record: dict[str, Any], game: XiangqiGame) -> dict[str, Any]:
    state = game.snapshot()
    if record["status"] != "active":
        state["legal_moves"] = []
    return {"game_id": record["game_id"], "game_type": "xiangqi",
            "status": record["status"], "state": state,
            "moves": list(record["moves"][-24:]), "outcome": record["outcome"]}
