"""An exploitative heads-up bot.

Each decision compares the estimated value of folding, calling and several
raise sizes. The estimates come from simulating the hand against a range of
opponent hands, and that range and the opponent's fold, call and raise rates
are learned from how the opponent has played so far.
"""

import random
import time

from card_utils import SUITS
from fast_eval import score_hand
from player_action import DEALER, PlayerAction
from preflop_table import EQUITY

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
                if self.board and self._puts_them_all_in(state, total):
                    premium = POSTFLOP_SHOVE_PREMIUM
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
