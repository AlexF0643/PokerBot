import itertools
import random
from collections import Counter

import pytest

from card_utils import CATEGORIES, Card, evaluate, full_deck
from fast_eval import score_hand
from model import card_id

DECK = full_deck()


def score(text):
    return score_hand([card_id(Card.parse(card)) for card in text.split()])


def test_card_ids_cover_the_deck():
    assert sorted(card_id(card) for card in DECK) == list(range(52))


def test_every_five_card_hand_matches_known_counts():
    """Check all 2,598,960 hands against the published combinatorics."""
    categories = Counter()
    scores = set()
    for hand in itertools.combinations(range(52), 5):
        value = score_hand(hand)
        categories[value >> 20] += 1
        scores.add(value)

    assert {CATEGORIES[key]: count for key, count in categories.items()} == {
        "straight_flush": 40,
        "four_of_a_kind": 624,
        "full_house": 3744,
        "flush": 5108,
        "straight": 10200,
        "three_of_a_kind": 54912,
        "two_pair": 123552,
        "pair": 1098240,
        "high_card": 1302540,
    }
    assert len(scores) == 7462


@pytest.mark.parametrize("size", [5, 6, 7])
def test_agrees_with_the_engine_evaluator(size):
    """The engine decides who wins, so comparisons must match it exactly."""
    rng = random.Random(size)
    for _ in range(3000):
        cards = rng.sample(DECK, size + 2)
        board = cards[2:size]
        first = cards[:2] + board
        second = cards[size:] + board
        official = evaluate(first), evaluate(second)
        fast = (
            score_hand([card_id(card) for card in first]),
            score_hand([card_id(card) for card in second]),
        )
        assert (official[0] > official[1]) == (fast[0] > fast[1])
        assert (official[0] == official[1]) == (fast[0] == fast[1])
        assert official[0][0] == fast[0] >> 20


@pytest.mark.parametrize(
    ("seven_cards", "best_five"),
    [
        ("KC KD KH 7S 7D 7H 2C", "KC KD KH 7S 7D"),
        ("AC AD KC KD QC QD 2H", "AC AD KC KD QC"),
        ("9C 9D 9H 9S KD KH KC", "9C 9D 9H 9S KD"),
        ("AC 2D 3H 4S 5D 6C 7D", "3H 4S 5D 6C 7D"),
    ],
)
def test_seven_card_edge_cases(seven_cards, best_five):
    assert score(seven_cards) == score(best_five)


def test_wheel_is_the_lowest_straight():
    assert score("6C 5D 4H 3S 2D") > score("5C 4D 3H 2S AD")
