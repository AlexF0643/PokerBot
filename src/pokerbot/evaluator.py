"""Poker hand evaluation for 5, 6 or 7 cards.

A score packs the hand category and up to five tie-break ranks into one int, so
hands compare with ordinary integer comparison:

    category << 20 | r1 << 16 | r2 << 12 | r3 << 8 | r4 << 4 | r5

Unused tie-break slots are zero, so equal hands always have equal scores.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import IntEnum


class HandCategory(IntEnum):
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    TRIPS = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    QUADS = 7
    STRAIGHT_FLUSH = 8


_ACE = 12
_FIVE = 3
_WHEEL_MASK = 1 << _ACE | 0b1111


def _build_straight_high() -> list[int]:
    """Map each 13-bit rank mask to its best straight's high rank, or -1."""
    table = [-1] * (1 << 13)
    for mask in range(1 << 13):
        if mask & _WHEEL_MASK == _WHEEL_MASK:
            table[mask] = _FIVE
        for low in range(9):
            if mask >> low & 0b11111 == 0b11111:
                table[mask] = low + 4
    return table


def _build_ranks_desc() -> list[tuple[int, ...]]:
    """Map each 13-bit rank mask to its ranks, highest first."""
    return [
        tuple(rank for rank in range(_ACE, -1, -1) if mask >> rank & 1)
        for mask in range(1 << 13)
    ]


_STRAIGHT_HIGH = _build_straight_high()
_RANKS_DESC = _build_ranks_desc()


def _score(category: HandCategory, *ranks: int) -> int:
    score = int(category)
    for rank in ranks:
        score = score << 4 | rank
    return score << 4 * (5 - len(ranks))


def evaluate_unchecked(cards: Sequence[int]) -> int:
    """Score 5 to 7 distinct cards without validating them, for hot loops."""
    rank_mask = 0
    suit_masks = [0, 0, 0, 0]
    counts = [0] * 13
    for card in cards:
        rank = card >> 2
        bit = 1 << rank
        rank_mask |= bit
        suit_masks[card & 3] |= bit
        counts[rank] += 1

    # Seven cards can't hold a flush together with quads or a full house, so a
    # flush can be returned without checking those.
    for suit_mask in suit_masks:
        if suit_mask.bit_count() >= 5:
            high = _STRAIGHT_HIGH[suit_mask]
            if high >= 0:
                return _score(HandCategory.STRAIGHT_FLUSH, high)
            return _score(HandCategory.FLUSH, *_RANKS_DESC[suit_mask][:5])

    quads = -1
    trips: list[int] = []
    pairs: list[int] = []
    singles: list[int] = []
    ranks = _RANKS_DESC[rank_mask]
    for rank in ranks:
        count = counts[rank]
        if count == 1:
            singles.append(rank)
        elif count == 2:
            pairs.append(rank)
        elif count == 3:
            trips.append(rank)
        else:
            quads = rank

    if quads >= 0:
        kicker = next(rank for rank in ranks if rank != quads)
        return _score(HandCategory.QUADS, quads, kicker)

    if trips and (pairs or len(trips) > 1):
        # With 7 cards, a second set of trips can supply the pair.
        pair = max(trips[1:] + pairs[:1])
        return _score(HandCategory.FULL_HOUSE, trips[0], pair)

    high = _STRAIGHT_HIGH[rank_mask]
    if high >= 0:
        return _score(HandCategory.STRAIGHT, high)

    if trips:
        return _score(HandCategory.TRIPS, trips[0], *singles[:2])

    if len(pairs) >= 2:
        # A third pair's rank can be the kicker.
        kicker = max(pairs[2:3] + singles[:1])
        return _score(HandCategory.TWO_PAIR, pairs[0], pairs[1], kicker)

    if pairs:
        return _score(HandCategory.PAIR, pairs[0], *singles[:3])

    return _score(HandCategory.HIGH_CARD, *singles[:5])


def evaluate(cards: Sequence[int]) -> int:
    """Score the best five-card hand from 5 to 7 distinct cards."""
    if not 5 <= len(cards) <= 7:
        raise ValueError(f"expected 5 to 7 cards, got {len(cards)}")
    if len(set(cards)) != len(cards):
        raise ValueError("cards must be distinct")
    if any(not 0 <= card < 52 for card in cards):
        raise ValueError("card ids must be in 0..51")
    return evaluate_unchecked(cards)


def hand_category(score: int) -> HandCategory:
    """Return the category of a score from :func:`evaluate`."""
    return HandCategory(score >> 20)
