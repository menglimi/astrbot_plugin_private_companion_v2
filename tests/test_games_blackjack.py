from __future__ import annotations

import pytest

from companion_v2.games import BlackjackCard, BlackjackGame
from companion_v2.games.blackjack import _best_value, fresh_shoe


def fixed_shoe(ranks: list[str]) -> list[BlackjackCard]:
    suits = ("♠", "♥", "♦", "♣")
    return [
        BlackjackCard(rank=rank, suit=suits[index % 4])
        for index, rank in enumerate(reversed(ranks))
    ]


def test_fresh_shoe_contains_six_complete_decks() -> None:
    shoe = fresh_shoe()

    assert len(shoe) == 6 * 52
    assert len({(card.rank, card.suit) for card in shoe}) == 52
    assert sum(card.rank == "A" for card in shoe) == 24


@pytest.mark.parametrize(
    ("cards", "expected"),
    [
        ([BlackjackCard("A", "♠"), BlackjackCard("7", "♥")], (18, True)),
        ([BlackjackCard("A", "♠"), BlackjackCard("6", "♥")], (17, True)),
        ([BlackjackCard("A", "♠"), BlackjackCard("10", "♥"), BlackjackCard("A", "♦")], (12, False)),
        ([BlackjackCard("K", "♠"), BlackjackCard("Q", "♥"), BlackjackCard("5", "♦")], (25, False)),
    ],
)
def test_best_value_handles_soft_and_bust_totals(
    cards: list[BlackjackCard], expected: tuple[int, bool]
) -> None:
    assert _best_value(cards) == expected


def test_deal_gives_each_player_two_cards_and_hides_dealer_hole_card() -> None:
    game = BlackjackGame.deal(
        difficulty="normal",
        player_numbers=[1, 2],
        shoe=fixed_shoe(["A", "2", "K", "9", "7", "5", "3", "4"]),
    )

    assert [card.rank for card in game.hands[1].cards] == ["A", "2"]
    assert game.hands[1].value == 13
    assert game.dealer_cards[0].rank == "7"
    assert game.dealer_hole is not None and game.dealer_hole.rank == "5"
    assert game.snapshot()["dealer_hidden"] is True
    assert len(game.snapshot()["dealer_cards"]) == 1


def test_natural_blackjack_is_recognised_at_deal_time() -> None:
    game = BlackjackGame.deal(
        difficulty="normal", player_numbers=[1], shoe=fixed_shoe(["A", "K", "9", "8"])
    )

    assert game.hands[1].blackjack
    assert game.hands[1].status == "blackjack"
    assert game.all_players_done()


def test_dealer_natural_is_peeked_and_settled_immediately() -> None:
    game = BlackjackGame.deal(
        difficulty="normal", player_numbers=[1], shoe=fixed_shoe(["10", "3", "K", "A"])
    )

    assert game.dealer_blackjack
    assert game.finished
    assert game.phase == "settled"
    assert game.results == {1: "loss"}
    assert game.snapshot()["dealer_hidden"] is False


def test_hit_handles_bust_and_auto_stand_at_twenty_one() -> None:
    game = BlackjackGame.deal(
        difficulty="normal", player_numbers=[1], shoe=fixed_shoe(["10", "6", "9", "8", "4", "5"])
    )

    assert game.hit(1)["value"] == 20
    game.hit(1)
    assert game.hands[1].busted
    assert game.hands[1].result == "loss"

    game = BlackjackGame.deal(
        difficulty="normal", player_numbers=[1], shoe=fixed_shoe(["10", "6", "9", "8", "5"])
    )
    game.hit(1)
    assert game.hands[1].value == 21
    assert game.hands[1].status == "stand"


@pytest.mark.parametrize(
    ("difficulty", "must_hit"),
    [("easy", False), ("normal", False), ("hard", True)],
)
def test_dealer_soft_seventeen_policy(difficulty: str, must_hit: bool) -> None:
    game = BlackjackGame.deal(
        difficulty=difficulty, player_numbers=[1], shoe=fixed_shoe(["9", "5", "A", "6", "2"])
    )
    game.stand(1)
    game.phase = "dealer_turn"

    assert game.dealer_total == 17
    assert game.dealer_soft
    assert game.dealer_must_hit is must_hit


@pytest.mark.parametrize(
    ("ranks", "expected"),
    [
        (["7", "7", "9", "2", "2", "2", "K"], "win"),
        (["10", "10", "10", "10", "2"], "push"),
        (["10", "9", "10", "10", "2"], "loss"),
    ],
)
def test_settlement_compares_player_and_dealer_totals(
    ranks: list[str], expected: str
) -> None:
    game = BlackjackGame.deal(
        difficulty="normal", player_numbers=[1], shoe=fixed_shoe(ranks)
    )
    game.stand(1)
    game.phase = "dealer_turn"
    while game.dealer_must_hit:
        game.draw_dealer()

    assert game.settle() == {1: expected}
    assert game.finished


def test_natural_blackjack_beats_a_drawn_dealer_twenty_one() -> None:
    game = BlackjackGame.deal(
        difficulty="normal", player_numbers=[1], shoe=fixed_shoe(["A", "K", "3", "8", "10"])
    )
    game.phase = "dealer_turn"
    while game.dealer_must_hit:
        game.draw_dealer()
    game.settle()

    assert game.dealer_total == 21
    assert game.results == {1: "blackjack_win"}


def test_surrender_marks_the_hand_as_a_loss() -> None:
    game = BlackjackGame.deal(
        difficulty="normal", player_numbers=[1, 2], shoe=fixed_shoe(["10", "6", "10", "8", "9", "8"])
    )

    game.surrender(1)

    assert game.hands[1].status == "surrendered"
    assert game.hands[1].result == "loss"
    assert not game.all_players_done()


@pytest.mark.parametrize("player_numbers", [[], [1, 1]])
def test_deal_rejects_empty_or_duplicate_players(player_numbers: list[int]) -> None:
    with pytest.raises(ValueError, match="玩家编号"):
        BlackjackGame.deal(player_numbers=player_numbers)
