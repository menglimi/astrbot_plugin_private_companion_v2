"""Small public game facts and durable times for conversation continuity."""

from __future__ import annotations

import math


GAME_LABELS = {
    "tictactoe": "井字棋", "gomoku": "五子棋", "xiangqi": "中国象棋",
    "pig_dice": "掷骰竞分", "blackjack": "二十一点",
    "turtle_soup": "海龟汤", "draw_guess": "你画我猜",
}
SNAPSHOT_ACTIONS = {f"game.{kind}.snapshot": kind for kind in GAME_LABELS}
PUBLIC_STATE_FIELDS = (
    "turn", "human_mark", "bot_mark", "human_color", "bot_color", "human_side", "bot_side",
    "move_count", "human_score", "bot_score", "target_score", "turn_total", "last_roll",
    "phase", "dealer_hidden", "dealer_total", "results", "question_count", "hint_count",
    "guess_count", "max_guesses", "solved", "timed_out", "remaining_seconds",
)


def recorded_time(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value > 0 else None


def stamp_game_changes(previous, draft, now):
    """Only a changed game advances its clock; lookups and replays do not."""
    for scope, rooms in draft.items():
        for game_id, room in rooms.items():
            before = previous.get(scope, {}).get(game_id)
            if before == room:
                continue
            if before is None:
                room["created_at"] = now
            room["updated_at"] = now
            if (room["status"] in {"finished", "closed"}
                    and (before is None or before["status"] != room["status"])):
                room["ended_at"] = now


def conversation_records(rooms, kinds, *, now, result_ttl):
    """Keep the active game and latest result per kind in actual update order."""
    ordered = sorted(enumerate(rooms.values()),
                     key=lambda item: (recorded_time(item[1].get("updated_at")) or 0, item[0]))
    selected = []
    for kind in GAME_LABELS:
        if kind not in kinds:
            continue
        matching = [room for _, room in ordered if room.get("game_type", "tictactoe") == kind]
        active = next((room for room in reversed(matching) if room["status"] == "active"), None)
        recent = next((room for room in reversed(matching) if room["status"] == "finished"), None)
        if recent is None:
            recent = next((room for room in reversed(matching) if room["status"] == "closed"), None)
        if recent is not None and result_ttl > 0:
            ended = recorded_time(recent.get("ended_at"))
            # Old ledgers have no per-game time. Preserve their latest real
            # result, explicitly without claiming when it happened.
            if ended is None or now - ended <= result_ttl:
                selected.append(recent)
        if active is not None:
            selected.append(active)
    selected_ids = {room["game_id"] for room in selected}
    return [room for _, room in ordered if room["game_id"] in selected_ids]


def public_game_fact(record, view=None):
    """Project public progress only; never copy a shoe, solution or target."""
    kind = record.get("game_type", "tictactoe")
    status = record["status"]
    outcome = record.get("outcome")
    result = "尚未结束，胜负未定" if status == "active" else "已关闭，未判定胜负"
    if status == "finished":
        if kind in {"turtle_soup", "draw_guess"}:
            result = "本局结束，当前用户已解答成功" if outcome == "player" else "本局结束，当前用户未解答成功"
        else:
            result = {"player": "本局结束，当前用户获胜、当前角色落败",
                      "bot": "本局结束，当前角色获胜、当前用户落败",
                      "draw": "本局结束，双方平局"}.get(outcome, "本局结束，胜负未记录")
    fact = {"game_id": record["game_id"], "game_type": kind, "game_name": GAME_LABELS[kind],
            "status": status, "outcome": outcome, "result": result,
            "updated_at": recorded_time(record.get("updated_at")),
            "ended_at": recorded_time(record.get("ended_at"))}
    if kind in {"gomoku", "xiangqi"}:
        human = record.get("human_side", "black" if kind == "gomoku" else "red")
        sides = {"black": "黑棋", "white": "白棋"} if kind == "gomoku" else {"red": "红方", "black": "黑方"}
        fact["user_side"] = sides[human]
        fact["role_side"] = next(label for side, label in sides.items() if side != human)
    if "moves" in record:
        fact["move_count"] = len(record["moves"])
    if view is not None:
        state = view["state"]
        fact["progress"] = {key: state[key] for key in PUBLIC_STATE_FIELDS if key in state}
    return fact
