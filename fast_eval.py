"""A fast hand evaluator for simulations, working on integer cards.

A card is ``rank * 4 + suit``, with ranks 0 (two) to 12 (ace). A score packs
the category and up to five tie-break ranks into one int, so higher scores win
and equal scores split:

    category << 20 | r1 << 16 | r2 << 12 | r3 << 8 | r4 << 4 | r5

Categories match ``card_utils.CATEGORIES``, from 0 (high card) to 8 (straight
flush). The caller must pass 5 to 7 distinct cards: nothing is validated.
"""

_ACE = 12
_FIVE = 3
_WHEEL_MASK = 1 << _ACE | 0b1111


def _build_straight_high():
    """Map each 13-bit rank mask to its best straight's high rank, or -1."""
    table = [-1] * (1 << 13)
    for mask in range(1 << 13):
        if mask & _WHEEL_MASK == _WHEEL_MASK:
            table[mask] = _FIVE
        for low in range(9):
            if mask >> low & 0b11111 == 0b11111:
                table[mask] = low + 4
    return table


def _build_ranks_desc():
    """Map each 13-bit rank mask to its ranks, highest first."""
    return [
        tuple(rank for rank in range(_ACE, -1, -1) if mask >> rank & 1)
        for mask in range(1 << 13)
    ]


_STRAIGHT_HIGH = _build_straight_high()
_RANKS_DESC = _build_ranks_desc()


def _score(category, *ranks):
    score = category
    for rank in ranks:
        score = score << 4 | rank
    return score << 4 * (5 - len(ranks))


def score_hand(cards):
    """Score the best five-card hand among 5 to 7 distinct integer cards."""
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
                return _score(8, high)
            return _score(5, *_RANKS_DESC[suit_mask][:5])

    quads = -1
    trips = []
    pairs = []
    singles = []
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
        return _score(7, quads, kicker)

    if trips and (pairs or len(trips) > 1):
        # With 7 cards, a second set of trips can supply the pair.
        return _score(6, trips[0], max(trips[1:] + pairs[:1]))

    high = _STRAIGHT_HIGH[rank_mask]
    if high >= 0:
        return _score(4, high)

    if trips:
        return _score(3, trips[0], *singles[:2])

    if len(pairs) >= 2:
        # A third pair's rank can be the kicker.
        return _score(2, pairs[0], pairs[1], max(pairs[2:3] + singles[:1]))

    if pairs:
        return _score(1, pairs[0], *singles[:3])

    return _score(0, *singles[:5])
