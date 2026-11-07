import itertools
import random
from collections import Counter

import pytest

from pokerbot import HandCategory, evaluate, hand_category, parse_cards


def score(text):
    return evaluate(parse_cards(text))


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("As Ks Qs Js Ts", HandCategory.STRAIGHT_FLUSH),
        ("5h 4h 3h 2h Ah", HandCategory.STRAIGHT_FLUSH),
        ("9c 9d 9h 9s 2d", HandCategory.QUADS),
        ("9c 9d 9h 2s 2d", HandCategory.FULL_HOUSE),
        ("As Js 9s 5s 2s", HandCategory.FLUSH),
        ("Tc 9d 8h 7s 6d", HandCategory.STRAIGHT),
        ("5c 4d 3h 2s Ad", HandCategory.STRAIGHT),
        ("9c 9d 9h 3s 2d", HandCategory.TRIPS),
        ("9c 9d 3h 3s 2d", HandCategory.TWO_PAIR),
        ("9c 9d 4h 3s 2d", HandCategory.PAIR),
        ("Ac 9d 7h 3s 2d", HandCategory.HIGH_CARD),
    ],
)
def test_categories(text, category):
    assert hand_category(score(text)) == category


@pytest.mark.parametrize(
    ("stronger", "weaker"),
    [
        # Categories in order.
        ("2c 3c 4c 5c 6c", "As Ad Ah Ac Kd"),
        ("2c 2d 2h 2s 3d", "As Ad Ah Kc Kd"),
        ("2c 2d 2h 3s 3d", "As Ks Qs Js 9s"),
        ("2s 3s 4s 5s 7s", "As Kd Qh Jc Td"),
        ("5c 4d 3h 2s Ad", "As Ad Ah Kc Qd"),
        ("2c 2d 2h 3s 4d", "As Ad Kh Kc Qd"),
        ("2c 2d 3h 3s 4d", "As Ad Kh Qc Jd"),
        ("2c 2d 3h 4s 5d", "As Kd Qh Jc 9d"),
        # The wheel is the lowest straight, and an ace-high one the highest.
        ("6c 5d 4h 3s 2d", "5c 4d 3h 2s Ad"),
        ("As Kd Qh Jc Td", "Kc Qd Jh Ts 9d"),
        ("6h 5h 4h 3h 2h", "5s 4s 3s 2s As"),
        # Tie-breaks within a category.
        ("3c 3d 3h 3s 5d", "3c 3d 3h 3s 4d"),
        ("3c 3d 3h 2s 2d", "2c 2d 2h As Ad"),
        ("As Js 9s 5s 3s", "Ad Jd 9d 5d 2d"),
        ("9c 9d 9h As 2d", "9c 9d 9h Ks Qd"),
        ("Tc Td 2h 2s 3d", "9c 9d 8h 8s Ad"),
        ("Ac Ad 8h 8s 7d", "Ac Ad 8h 8s 6d"),
        ("9c 9d Ah 3s 2d", "9c 9d Kh Qs Jd"),
        ("9c 9d Ah Ks 3d", "9h 9s Ad Kc 2d"),
        ("Ac Kd Qh Js 9d", "Ac Kd Qh Js 8d"),
    ],
)
def test_ordering(stronger, weaker):
    assert score(stronger) > score(weaker)


def test_suits_do_not_break_ties():
    assert score("As Kd Qh Jc 9d") == score("Ah Kc Qd Js 9c")


@pytest.mark.parametrize(
    ("seven_cards", "best_five"),
    [
        # Two sets of trips make a full house using the higher set.
        ("Kc Kd Kh 7s 7d 7h 2c", "Kc Kd Kh 7s 7d"),
        # Three pairs use the best kicker, which can come from the third pair.
        ("Ac Ad Kc Kd Qc Qd 2h", "Ac Ad Kc Kd Qc"),
        ("Ac Ad Kc Kd 3c 3d 5h", "Ac Ad Kc Kd 5h"),
        # With trips and two pairs, a full house uses the higher pair.
        ("Kc Kd Kh Qs Qd 2h 2c", "Kc Kd Kh Qs Qd"),
        # Quads take the highest kicker, even from a pair or trips.
        ("9c 9d 9h 9s Ad Ah 2c", "9c 9d 9h 9s Ad"),
        ("9c 9d 9h 9s Kd Kh Kc", "9c 9d 9h 9s Kd"),
        # A sixth and seventh suited card only matter when they rank higher.
        ("As Qs 9s 7s 5s 3s 2s", "As Qs 9s 7s 5s"),
        # A straight flush beats a higher, non-flush straight.
        ("8h 7h 6h 5h 4h 9c Tc", "8h 7h 6h 5h 4h"),
        # A flush and a separate straight are not a straight flush.
        ("Ah Kh Qh Jh 9h Tc 2d", "Ah Kh Qh Jh 9h"),
        # The higher straight wins over a wheel in the same seven cards.
        ("Ac 2d 3h 4s 5d 6c 7d", "3h 4s 5d 6c 7d"),
    ],
)
def test_seven_card_best_hand(seven_cards, best_five):
    assert score(seven_cards) == score(best_five)


def test_every_five_card_hand_matches_known_counts():
    """Check all 2,598,960 hands against the published combinatorics."""
    categories = Counter()
    distinct_scores = set()
    for hand in itertools.combinations(range(52), 5):
        hand_score = evaluate(hand)
        categories[hand_category(hand_score)] += 1
        distinct_scores.add(hand_score)

    assert categories == {
        HandCategory.STRAIGHT_FLUSH: 40,
        HandCategory.QUADS: 624,
        HandCategory.FULL_HOUSE: 3744,
        HandCategory.FLUSH: 5108,
        HandCategory.STRAIGHT: 10200,
        HandCategory.TRIPS: 54912,
        HandCategory.TWO_PAIR: 123552,
        HandCategory.PAIR: 1098240,
        HandCategory.HIGH_CARD: 1302540,
    }
    assert len(distinct_scores) == 7462


@pytest.mark.parametrize("size", [6, 7])
def test_larger_hands_match_best_five_card_subset(size):
    rng = random.Random(size)
    for _ in range(20000):
        cards = rng.sample(range(52), size)
        best_subset = max(evaluate(c) for c in itertools.combinations(cards, 5))
        assert evaluate(cards) == best_subset


@pytest.mark.parametrize(
    "cards",
    [
        [0, 1, 2, 3],
        list(range(8)),
        [0, 0, 1, 2, 3],
        [0, 1, 2, 3, 52],
        [-1, 0, 1, 2, 3],
    ],
)
def test_evaluate_rejects_invalid_input(cards):
    with pytest.raises(ValueError):
        evaluate(cards)
