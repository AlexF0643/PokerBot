"""An exploitative heads-up bot.

Each decision compares the estimated value of folding, calling and several
raise sizes. The estimates come from simulating the hand against a range of
opponent hands, and that range and the opponent's fold, call and raise rates
are learned from how the opponent has played so far.
"""

import random
import time

from card_utils import SUITS
from player_action import DEALER, PlayerAction

# -- hand evaluation ---------------------------------------------------
#
# A card is rank * 4 + suit, with ranks 0 (two) to 12 (ace). A score packs
# the category and up to five tie-break ranks into one int, so higher scores
# win and equal scores split. Categories match card_utils.CATEGORIES.
# score_hand needs 5 to 7 distinct cards and validates nothing, for speed.

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


# Heads-up equity of each starting hand against a random hand, from
# tools/build_preflop_table.py.
EQUITY = {
    "AA": 0.8469,
    "KK": 0.8220,
    "QQ": 0.8020,
    "JJ": 0.7762,
    "TT": 0.7491,
    "99": 0.7221,
    "88": 0.6873,
    "77": 0.6685,
    "AKs": 0.6684,
    "AQs": 0.6620,
    "AKo": 0.6540,
    "AJs": 0.6538,
    "AQo": 0.6476,
    "ATs": 0.6421,
    "AJo": 0.6334,
    "A9s": 0.6323,
    "KQs": 0.6308,
    "66": 0.6290,
    "ATo": 0.6244,
    "KJs": 0.6194,
    "A8s": 0.6188,
    "KTs": 0.6153,
    "KQo": 0.6151,
    "A7s": 0.6087,
    "A9o": 0.6048,
    "A6s": 0.6018,
    "A5s": 0.6005,
    "KJo": 0.6002,
    "55": 0.5998,
    "QJs": 0.5991,
    "KTo": 0.5959,
    "K9s": 0.5953,
    "QTs": 0.5926,
    "A8o": 0.5923,
    "A7o": 0.5884,
    "A4s": 0.5866,
    "K8s": 0.5850,
    "A5o": 0.5814,
    "A6o": 0.5813,
    "A3s": 0.5808,
    "QJo": 0.5807,
    "A2s": 0.5792,
    "K9o": 0.5786,
    "K7s": 0.5775,
    "JTs": 0.5769,
    "Q9s": 0.5764,
    "QTo": 0.5758,
    "K6s": 0.5712,
    "A4o": 0.5685,
    "44": 0.5662,
    "K5s": 0.5617,
    "K8o": 0.5614,
    "Q8s": 0.5608,
    "JTo": 0.5573,
    "J9s": 0.5564,
    "K7o": 0.5558,
    "Q9o": 0.5536,
    "A3o": 0.5530,
    "A2o": 0.5512,
    "K4s": 0.5481,
    "T9s": 0.5436,
    "K3s": 0.5409,
    "K6o": 0.5401,
    "Q7s": 0.5381,
    "Q8o": 0.5380,
    "J8s": 0.5373,
    "J9o": 0.5347,
    "K5o": 0.5339,
    "33": 0.5326,
    "Q6s": 0.5326,
    "Q5s": 0.5306,
    "K2s": 0.5275,
    "T8s": 0.5252,
    "Q7o": 0.5233,
    "J7s": 0.5216,
    "Q4s": 0.5208,
    "K4o": 0.5179,
    "T9o": 0.5168,
    "K3o": 0.5150,
    "Q6o": 0.5125,
    "J8o": 0.5105,
    "22": 0.5087,
    "K2o": 0.5081,
    "Q3s": 0.5066,
    "Q5o": 0.5065,
    "T7s": 0.5044,
    "J6s": 0.5036,
    "98s": 0.5027,
    "Q2s": 0.5021,
    "J5s": 0.5012,
    "J7o": 0.5006,
    "T8o": 0.4954,
    "97s": 0.4919,
    "Q4o": 0.4883,
    "J4s": 0.4881,
    "T6s": 0.4840,
    "J6o": 0.4828,
    "98o": 0.4828,
    "J3s": 0.4824,
    "Q3o": 0.4807,
    "T7o": 0.4804,
    "87s": 0.4784,
    "Q2o": 0.4735,
    "96s": 0.4712,
    "J5o": 0.4702,
    "J2s": 0.4683,
    "T5s": 0.4677,
    "97o": 0.4674,
    "J4o": 0.4635,
    "T6o": 0.4618,
    "T4s": 0.4617,
    "86s": 0.4612,
    "T3s": 0.4604,
    "95s": 0.4562,
    "J3o": 0.4546,
    "76s": 0.4543,
    "96o": 0.4497,
    "85s": 0.4468,
    "87o": 0.4466,
    "T2s": 0.4460,
    "T5o": 0.4459,
    "94s": 0.4412,
    "J2o": 0.4408,
    "86o": 0.4367,
    "75s": 0.4362,
    "T4o": 0.4345,
    "65s": 0.4338,
    "T3o": 0.4326,
    "93s": 0.4285,
    "84s": 0.4264,
    "76o": 0.4257,
    "95o": 0.4238,
    "74s": 0.4211,
    "92s": 0.4206,
    "64s": 0.4171,
    "85o": 0.4161,
    "T2o": 0.4153,
    "54s": 0.4152,
    "83s": 0.4151,
    "94o": 0.4097,
    "75o": 0.4068,
    "73s": 0.4052,
    "82s": 0.4026,
    "93o": 0.4012,
    "65o": 0.3993,
    "53s": 0.3967,
    "84o": 0.3934,
    "63s": 0.3926,
    "43s": 0.3880,
    "92o": 0.3867,
    "74o": 0.3837,
    "54o": 0.3829,
    "72s": 0.3822,
    "52s": 0.3787,
    "64o": 0.3749,
    "62s": 0.3749,
    "83o": 0.3720,
    "82o": 0.3704,
    "42s": 0.3664,
    "63o": 0.3647,
    "53o": 0.3638,
    "73o": 0.3616,
    "32s": 0.3607,
    "43o": 0.3503,
    "52o": 0.3422,
    "72o": 0.3419,
    "62o": 0.3401,
    "42o": 0.3337,
    "32o": 0.3260,
}

RANKS = "23456789TJQKA"

SIMULATIONS = 600
THINK_SECONDS = 4.0  # the limit is 10 s per move, on an unknown machine

# Prior opponent rates per decision point, as (fold, call, raise, shove). Each
# counts for PRIOR_WEIGHT hands, then real observations take over.
#   open: first to act preflop      versus_raise: facing our preflop raise
#   versus_limp: after our limp     check_or_bet: postflop, nothing to call
#   versus_bet: postflop, facing our bet or raise
#   versus_reraise: facing our raise, having already raised this street
#   all_in_preflop, all_in_postflop: facing a raise that puts them all-in
PRIORS = {
    "all_in_preflop": (0.55, 0.45, 0.0, 0.0),
    "all_in_postflop": (0.35, 0.65, 0.0, 0.0),
    "versus_reraise": (0.20, 0.50, 0.20, 0.10),
    "open": (0.25, 0.35, 0.35, 0.05),
    "versus_raise": (0.40, 0.42, 0.12, 0.06),
    "versus_limp": (0.0, 0.70, 0.28, 0.02),
    "check_or_bet": (0.0, 0.55, 0.42, 0.03),
    "versus_bet": (0.42, 0.42, 0.12, 0.04),
}
PRIOR_WEIGHT = 14
ACTION_INDEX = {"fold": 0, "call": 1, "raise": 2, "shove": 3}

# How much of a hand's equity survives later betting without the last word.
REALIZED_IN_POSITION = 0.98
REALIZED_OUT_OF_POSITION = 0.88
PREFLOP_RAISE_SIZES = (2.5, 3.5)  # in big blinds when opening
RERAISE_MULTIPLE = 3.0
POT_FRACTIONS = (0.5, 0.75, 1.0)
# A raise must beat the best passive action by this much, because estimates
# run high and bigger bets have more riding on them.
RAISE_MARGIN = 2.0  # chips
RAISE_RISK_PREMIUM = 0.03  # share of the chips the raise adds
# Opponents choose to continue after seeing their cards, so hands that call a
# postflop raise beat us more often than ranking them by strength suggests.
# tools/calibrate.py measures this gap.
POSTFLOP_CALLED_EQUITY = 0.90
POSTFLOP_SHOVE_PREMIUM = 0.10  # replaces the premium for postflop all-ins
PREFLOP_SHOVE_PREMIUM = 0.03  # replaces the premium for preflop all-ins
MIN_CALLED_EQUITY = 0.30  # no all-in raise below this against likely callers

# What showdowns teach, as (prior share, weight in hands). Bluffs are bets made
# with weak hands; traps are strong hands played passively.
SHOWDOWN_LEARNING = 1.0  # 0.0 switches it off
BLUFF_PRIOR = (0.20, 6)
TRAP_PRIOR = (0.50, 6)
PREFLOP_BLUFF_PRIOR = (0.03, 6)


def card_id(card):
    """A Card as the integer that fast_eval uses."""
    return (card.value - 2) * 4 + SUITS.index(card.suit)


def _hand_name(first, second):
    high, low = max(first >> 2, second >> 2), min(first >> 2, second >> 2)
    if high == low:
        return RANKS[high] * 2
    suited = first & 3 == second & 3
    return RANKS[high] + RANKS[low] + ("s" if suited else "o")


def _combos_by_strength():
    """All 1326 starting hands as pairs of card ids, weakest first."""
    combos = [
        (first, second)
        for first in range(52)
        for second in range(first + 1, 52)
    ]
    combos.sort(key=lambda combo: EQUITY[_hand_name(*combo)])
    return combos


ALL_COMBOS = _combos_by_strength()
# An even spread of hands to measure a shown hand against on a board.
BOARD_SAMPLE = ALL_COMBOS[::9]


def _preflop_top_share(first, second):
    """The share of hands at least as strong as this one, from 0 to 1."""
    equity = EQUITY[_hand_name(first, second)]
    stronger = sum(1 for value in EQUITY.values() if value > equity)
    return stronger / len(EQUITY)


def _beats_share(combo, board):
    """The share of other hands this hand beats on this board."""
    taken = set(board) | set(combo)
    mine = score_hand([*combo, *board])
    beaten = total = 0
    for other in BOARD_SAMPLE:
        if other[0] in taken or other[1] in taken:
            continue
        total += 1
        beaten += score_hand([*other, *board]) < mine
    return beaten / max(1, total)


def _clamp(value, low, high):
    return max(low, min(high, value))


class Model:
    def __init__(self):
        self.rng = random.Random(20261107)
        self.stats = {}  # team name -> decision point -> action counts
        self.reads = {}  # team name -> what its shown hands revealed
        self.their_moves = []  # this hand: (board, kind) for each of theirs
        self.shown = []
        self.last_estimate = 0.0  # chips back expected from the last decision
        self.hand = []
        self.player_id = None
        self.my_cards = ()
        self.range = []
        self.board = []
        self.we_acted = False
        self.we_raised = False
        self.they_raised = False
        self.we_shoved = False

    def seed(self, hand, player_id):
        self.hand = hand
        self.player_id = player_id
        self.my_cards = tuple(card_id(card) for card in hand)
        self.range = [
            combo for combo in ALL_COMBOS
            if combo[0] not in self.my_cards and combo[1] not in self.my_cards
        ]
        self.board = []
        self.we_acted = False
        self.we_raised = False
        self.they_raised = False
        self.we_shoved = False
        self.their_moves = []
        self.shown = []

    def run(self, actions, game_state):
        try:
            if game_state.num_players != 2:
                return self._simple_action(game_state)
            self._observe(actions, game_state, True)
            return self._decide(game_state)
        except Exception:
            # An error must never cost a fault: this move is always legal.
            return self._check_or_fold(game_state)

    def end_game(self, actions, game_state):
        try:
            if game_state.num_players == 2:
                self._observe(actions, game_state, False)
        except Exception:
            pass

    # -- learning ------------------------------------------------------------

    def _rates(self, team, point):
        """(fold, call, raise, shove) rates at a decision point."""
        counts = self.stats.get(team, {}).get(point, (0, 0, 0, 0))
        total = sum(counts) + PRIOR_WEIGHT
        return tuple(
            (count + prior * PRIOR_WEIGHT) / total
            for count, prior in zip(counts, PRIORS[point])
        )

    def _observe(self, actions, game_state, in_turn):
        """Update the opponent's rates and range from the latest actions."""
        me = self.player_id
        opponent = 1 - me
        team = game_state.teams[opponent]
        for action in actions:
            if action.kind == "win":
                continue
            if action.kind == "reveal_card":
                if action.player_id == DEALER:
                    self.board.append(card_id(action.card))
                    if len(self.board) >= 3:
                        self.we_raised = False
                        self.they_raised = False
                elif action.player_id == opponent:
                    self.shown.append(card_id(action.card))
                continue
            if action.player_id == me:
                self.we_acted = True
                self.we_raised = action.kind == "raise"
                continue

            kind = action.kind
            # A raise always gets an answer from us, so during our turn the
            # opponent's stack shows whether it was all-in.
            if kind == "raise" and in_turn and not game_state.stacks[opponent]:
                kind = "shove"
            point = self._decision_point()
            self._count(team, point, kind)
            self._narrow_range(team, point, kind)
            self.their_moves.append((tuple(self.board), kind))
            self.we_raised = False
            if kind in ("raise", "shove"):
                self.they_raised = True
        if not in_turn and len(self.shown) == 2 and SHOWDOWN_LEARNING:
            self._learn_from_showdown(team)

    def _learn_from_showdown(self, team):
        """Record what the opponent's moves meant, now its cards are known."""
        reads = self.reads.setdefault(team, {
            "bluffs": 0, "value_bets": 0, "strong_bets": 0, "traps": 0,
            "preflop_raises": 0, "preflop_bluffs": 0,
        })
        combo = tuple(self.shown)
        for board, kind in self.their_moves:
            aggressive = kind in ("raise", "shove")
            if not board:
                if aggressive:
                    reads["preflop_raises"] += 1
                    if _preflop_top_share(*combo) > 0.5:
                        reads["preflop_bluffs"] += 1
                continue
            if kind == "fold":
                continue
            beaten = _beats_share(combo, board)
            if aggressive:
                reads["value_bets" if beaten >= 0.5 else "bluffs"] += 1
                reads["strong_bets"] += beaten >= 0.8
            elif beaten >= 0.8:
                reads["traps"] += 1

    def _read(self, team, part, whole, prior):
        """A share learned from showdowns, starting from a prior."""
        reads = self.reads.get(team, {})
        share, weight = prior
        hits = sum(reads.get(key, 0) for key in part)
        total = sum(reads.get(key, 0) for key in whole)
        return (hits + share * weight) / (total + weight)

    def _decision_point(self):
        if self.we_raised and self.we_shoved:
            return "all_in_postflop" if self.board else "all_in_preflop"
        if self.we_raised and self.they_raised:
            return "versus_reraise"
        if len(self.board) >= 3:
            return "versus_bet" if self.we_raised else "check_or_bet"
        if self.we_raised:
            return "versus_raise"
        return "versus_limp" if self.we_acted else "open"

    def _count(self, team, point, kind):
        points = self.stats.setdefault(team, {})
        counts = list(points.get(point, (0, 0, 0, 0)))
        counts[ACTION_INDEX[kind]] += 1
        points[point] = tuple(counts)

    def _narrow_range(self, team, point, kind):
        """Keep the slice of the range that plays this way, strongest first:
        shoves, then raises, then calls, then folds."""
        if kind == "fold":
            return
        _, call, raised, shove = self._rates(team, point)
        if self.board:
            self._sort_range()
            aggressive = raised + shove
            if kind == "call":
                # Some strong hands slow-play, and draws look weak but call.
                traps = self._read(
                    team, ("traps",), ("traps", "strong_bets"), TRAP_PRIOR
                )
                self._keep_slice(
                    aggressive * (1.0 - traps), aggressive + call, 0.25
                )
            else:
                bluffs = self._read(
                    team, ("bluffs",), ("bluffs", "value_bets"), BLUFF_PRIOR
                )
                self._keep_slice(0.0, aggressive, _clamp(bluffs, 0.05, 0.9))
        elif kind == "shove":
            self._keep_slice(0.0, shove, self._preflop_bluffs(team))
        elif kind == "raise":
            self._keep_slice(
                shove * 0.5, shove + raised, self._preflop_bluffs(team)
            )
        else:
            self._keep_slice(shove + raised, shove + raised + call, 0.0)

    def _preflop_bluffs(self, team):
        return self._read(
            team, ("preflop_bluffs",), ("preflop_raises",), PREFLOP_BLUFF_PRIOR
        )

    def _keep_slice(self, top_low, top_high, keep_weaker):
        """Keep hands between two fractions from the top of the range, plus
        a random share of the weaker hands (bluffs and draws), in order."""
        size = len(self.range)
        top_high = max(top_high, top_low + 0.03)
        start = int(size * (1.0 - _clamp(top_high, 0.0, 1.0)))
        end = max(start + 1, int(size * (1.0 - _clamp(top_low, 0.0, 1.0)) + 0.5))
        if end - start < 8:
            start = max(0, end - 8)
        weaker = self.range[:start]
        kept = self.range[start:end]
        if keep_weaker and weaker:
            count = int(len(weaker) * keep_weaker)
            chosen = sorted(self.rng.sample(range(len(weaker)), count))
            kept = [weaker[index] for index in chosen] + kept
        self.range = kept

    def _sort_range(self):
        """Drop hands the board blocks and sort by current strength."""
        board = self.board
        taken = set(board)
        scored = [
            (score_hand([combo[0], combo[1], *board]), combo)
            for combo in self.range
            if combo[0] not in taken and combo[1] not in taken
        ]
        scored.sort()
        self.range = [combo for _, combo in scored]

    # -- deciding ------------------------------------------------------------

    def _simulate(self):
        """Our share of the pot against evenly spaced hands from the range,
        weakest first, so a slice of the result is a slice of the range."""
        if len(self.board) >= 3:
            self._sort_range()
        hands = self.range
        board = self.board
        mine = self.my_cards
        if len(board) == 5:
            my_score = score_hand([*mine, *board])
            count = len(hands)
        else:
            my_score = 0
            count = SIMULATIONS
        known = set(mine) | set(board)
        deck = [card for card in range(52) if card not in known]
        missing = 5 - len(board)
        deadline = time.perf_counter() + THINK_SECONDS
        sample = self.rng.sample
        outcomes = []
        for index in range(count):
            combo = hands[index * len(hands) // count]
            if missing:
                drawn = sample(deck, missing + 2)
                runout = [c for c in drawn if c not in combo][:missing]
                final = board + runout
                my_score = score_hand([*mine, *final])
            else:
                final = board
            their_score = score_hand([combo[0], combo[1], *final])
            outcomes.append(
                1.0 if my_score > their_score
                else 0.5 if my_score == their_score else 0.0
            )
            if not index % 64 and time.perf_counter() > deadline:
                raise TimeoutError("out of thinking time")
        return outcomes

    def _decide(self, state):
        me = self.player_id
        opponent = 1 - me
        team = state.teams[opponent]
        outcomes = self._simulate()
        prefix = [0.0]
        for outcome in outcomes:
            prefix.append(prefix[-1] + outcome)

        def equity(top_low, top_high):
            """Our equity against a slice of the range, by top fractions."""
            size = len(outcomes)
            start = int(size * (1.0 - _clamp(top_high, 0.0, 1.0)))
            end = int(size * (1.0 - _clamp(top_low, 0.0, 1.0)))
            start = min(start, size - 1)
            end = max(end, start + 1)
            return (prefix[end] - prefix[start]) / (end - start)

        pot = state.pot
        to_call = state.call_amount
        all_in_call = to_call >= state.stacks[me]
        if not self.board and to_call == 0 and not state.can_raise:
            return PlayerAction.call(me)
        if len(self.board) == 5 or all_in_call or not state.active_players:
            realized = 1.0
        elif me == state.button:
            realized = REALIZED_IN_POSITION
        else:
            realized = REALIZED_OUT_OF_POSITION
        call_value = equity(0.0, 1.0) * realized * (pot + to_call) - to_call
        passive_value = call_value if to_call == 0 else max(call_value, 0.0)
        best_kind = "call" if to_call == 0 or call_value > 0.0 else "fold"
        best_total = 0
        best_value = passive_value
        best_score = passive_value

        if state.can_raise:
            for total in self._raise_totals(state):
                value = self._raise_value(state, total, team, equity, realized)
                added = total - state.bets[me]
                premium = RAISE_RISK_PREMIUM
                if self._puts_them_all_in(state, total):
                    point = "all_in_postflop" if self.board else "all_in_preflop"
                    fold = self._rates(team, point)[0]
                    if equity(0.0, 1.0 - fold) < MIN_CALLED_EQUITY:
                        continue
                    premium = (
                        POSTFLOP_SHOVE_PREMIUM if self.board
                        else PREFLOP_SHOVE_PREMIUM
                    )
                score = value - RAISE_MARGIN - premium * added
                if score > best_score:
                    best_kind, best_total = "raise", total
                    best_value, best_score = value, score

        self.last_estimate = best_value
        if best_kind == "raise":
            self.we_shoved = self._puts_them_all_in(state, best_total)
            return PlayerAction.raise_to(me, best_total)
        if best_kind == "call":
            return PlayerAction.call(me)
        return PlayerAction.fold(me)

    def _puts_them_all_in(self, state, total):
        opponent = 1 - self.player_id
        return total >= state.bets[opponent] + state.stacks[opponent]

    def _raise_totals(self, state):
        """Legal raise totals to consider, capped at what can be called."""
        opponent = 1 - self.player_id
        low, high = state.raise_range
        cap = min(high, state.bets[opponent] + state.stacks[opponent])
        pot = state.pot
        if self.board:
            after_call = pot + state.call_amount
            totals = [
                state.current_bet + int(after_call * fraction)
                for fraction in POT_FRACTIONS
            ]
        elif state.current_bet <= state.big_blind:
            totals = [
                int(state.big_blind * size) for size in PREFLOP_RAISE_SIZES
            ]
        else:
            totals = [int(state.current_bet * RERAISE_MULTIPLE)]
        totals.append(cap)
        return sorted({_clamp(total, low, max(low, cap)) for total in totals})

    def _raise_value(self, state, total, team, equity, realized):
        """Estimated chips back from raising to total, against our rates."""
        me = self.player_id
        opponent = 1 - me
        pot = state.pot
        ours = total - state.bets[me]
        theirs = min(total - state.bets[opponent], state.stacks[opponent])
        if self._puts_them_all_in(state, total):
            # Nothing is left to bet, so no equity is lost on later streets.
            realized = 1.0
            point = "all_in_postflop" if self.board else "all_in_preflop"
            fold, _, raised, shove = self._rates(team, point)
        else:
            if self.they_raised:
                point = "versus_reraise"
            else:
                point = "versus_bet" if self.board else "versus_raise"
            fold, _, raised, shove = self._rates(team, point)
            # Bigger raises give worse odds to call, so they get more folds.
            price = theirs / max(1, pot + ours + theirs)
            fold = _clamp(fold * (0.9 + 0.35 * price), 0.0, 1.0)
        behind = state.stacks[me] - ours
        reraise = 0.0 if behind <= 0 else min(raised + shove, 1.0 - fold)
        called = 1.0 - fold - reraise

        value = fold * pot
        final_pot = pot + ours + theirs
        if called > 0.0:
            win_share = equity(reraise, reraise + called) * realized
            if self.board:
                win_share *= POSTFLOP_CALLED_EQUITY
            value += called * (win_share * final_pot - ours)
        if reraise > 0.0:
            extra = min(behind, int(ours * 1.5))
            share = equity(0.0, reraise)
            continued = share * (final_pot + 2 * extra) - ours - extra
            value += reraise * max(-ours, continued)
        return value

    # -- simple moves --------------------------------------------------------

    def _check_or_fold(self, state):
        if state.call_amount == 0:
            return PlayerAction.call(self.player_id)
        return PlayerAction.fold(self.player_id)

    def _simple_action(self, state):
        """Cautious play for more than two players, which the round never
        uses: the local validity test runs a full table."""
        if not state.board:
            strong = EQUITY[_hand_name(*self.my_cards)] >= 0.62
        else:
            board = [card_id(card) for card in state.board]
            strong = score_hand([*self.my_cards, *board]) >> 20 >= 1
        if strong and state.pot_odds < 0.34:
            return PlayerAction.call(self.player_id)
        return self._check_or_fold(state)
