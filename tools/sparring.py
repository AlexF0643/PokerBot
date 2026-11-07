"""Tougher practice opponents. Not part of the submission.

Each bot plays a style other teams might plausibly use, and several attack an
assumption our model makes, such as that bigger bets mean stronger hands.
"""

import random

from fast_eval import score_hand
from model import Model, _hand_name, card_id
from player_action import PlayerAction
from preflop_table import EQUITY
from tools import previous_model


class Base:
    samples = 150

    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.hands_played = 0
        self.player_id = None
        self.cards = ()

    def seed(self, hand, player_id):
        self.player_id = player_id
        self.cards = tuple(card_id(card) for card in hand)
        self.hands_played += 1

    def strength(self):
        """Preflop equity against a random hand."""
        return EQUITY[_hand_name(*self.cards)]

    def equity(self, state):
        """Equity against a random hand on the current board."""
        board = [card_id(card) for card in state.board]
        known = set(self.cards) | set(board)
        deck = [card for card in range(52) if card not in known]
        missing = 5 - len(board)
        won = 0.0
        for _ in range(self.samples):
            drawn = self.rng.sample(deck, missing + 2)
            final = board + drawn[2:]
            mine = score_hand([*self.cards, *final])
            theirs = score_hand([drawn[0], drawn[1], *final])
            won += 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0
        return won / self.samples

    def check_or_fold(self, state):
        if state.call_amount == 0:
            return PlayerAction.call(self.player_id)
        return PlayerAction.fold(self.player_id)

    def call(self):
        return PlayerAction.call(self.player_id)

    def raise_to(self, state, total):
        if not state.can_raise:
            return self.call()
        low, high = state.raise_range
        return PlayerAction.raise_to(self.player_id, min(high, max(low, total)))

    def bet_pot(self, state, fraction):
        size = int((state.pot + state.call_amount) * fraction)
        return self.raise_to(state, state.current_bet + size)

    def shove(self, state):
        return self.raise_to(state, state.max_raise_to)


class PushFold(Base):
    """Shoves or folds preflop, a popular short-stack plan."""

    def run(self, actions, state):
        strength = self.strength()
        if state.board:
            if self.equity(state) > 0.7:
                return self.shove(state)
            return self.check_or_fold(state)
        if state.call_amount == 0:
            return self.shove(state) if strength > 0.58 else self.call()
        if state.current_bet <= state.big_blind:
            return self.shove(state) if strength > 0.52 else self.check_or_fold(state)
        return self.shove(state) if strength > 0.60 else self.check_or_fold(state)


class Balanced(Base):
    """Sound ranges, value bets and a steady share of bluffs."""

    def run(self, actions, state):
        roll = self.rng.random()
        if not state.board:
            strength = self.strength()
            if state.call_amount == 0:
                if strength > 0.60 or roll < 0.1:
                    return self.raise_to(state, 3 * state.big_blind)
                return self.call()
            if state.current_bet <= state.big_blind:
                if strength > 0.42:
                    return self.raise_to(state, int(2.5 * state.big_blind))
                return self.check_or_fold(state)
            if state.current_bet >= 150:
                if strength > 0.66:
                    return self.shove(state)
                if strength > 0.60 and state.pot_odds < 0.4:
                    return self.call()
                return self.check_or_fold(state)
            if strength > 0.64 or roll < 0.03:
                return self.raise_to(state, 3 * state.current_bet)
            if strength > 0.47:
                return self.call()
            return self.check_or_fold(state)
        equity = self.equity(state)
        if state.call_amount == 0:
            if equity > 0.72 or (equity < 0.35 and roll < 0.25):
                return self.bet_pot(state, 0.66)
            return self.call()
        if equity > 0.9 or (equity < 0.3 and roll < 0.06):
            return self.bet_pot(state, 0.8)
        if equity > state.pot_odds + 0.12:
            return self.call()
        return self.check_or_fold(state)


class Maniac(Base):
    """Loose and aggressive, with frequent large bluffs."""

    def run(self, actions, state):
        roll = self.rng.random()
        if not state.board:
            strength = self.strength()
            if state.call_amount == 0:
                return self.raise_to(state, 4 * state.big_blind) if roll < 0.5 else self.call()
            if strength > 0.55 or roll < 0.3:
                return self.raise_to(state, 3 * state.current_bet)
            if strength > 0.40 or state.pot_odds < 0.3:
                return self.call()
            return self.check_or_fold(state)
        equity = self.equity(state)
        if state.call_amount == 0:
            return self.bet_pot(state, 1.0) if roll < 0.7 else self.call()
        if equity > 0.8 or roll < 0.15:
            return self.shove(state)
        if equity > state.pot_odds - 0.05:
            return self.call()
        return self.check_or_fold(state)


class Trapper(Base):
    """Slow-plays strong hands and bets its weak ones, inverting the signal
    that bets mean strength."""

    def run(self, actions, state):
        roll = self.rng.random()
        if not state.board:
            strength = self.strength()
            if state.call_amount == 0:
                return self.call()
            if strength > 0.45 or state.pot_odds < 0.25:
                return self.call()
            return self.check_or_fold(state)
        equity = self.equity(state)
        river = len(state.board) == 5
        if state.call_amount == 0:
            if equity < 0.4 and roll < 0.5:
                return self.bet_pot(state, 0.5)
            if river and equity > 0.8:
                return self.bet_pot(state, 1.0)
            return self.call()
        if equity > 0.85:
            return self.shove(state) if river else self.bet_pot(state, 1.0)
        if equity > state.pot_odds + 0.02:
            return self.call()
        return self.check_or_fold(state)


class Polarized(Base):
    """Small bets with medium hands, all-ins with its best hands and air."""

    def run(self, actions, state):
        roll = self.rng.random()
        if not state.board:
            strength = self.strength()
            if strength > 0.68 or (strength < 0.38 and roll < 0.12):
                return self.shove(state)
            if strength > 0.44:
                return self.call()
            return self.check_or_fold(state)
        equity = self.equity(state)
        if equity > 0.85 or (equity < 0.25 and roll < 0.2):
            return self.shove(state)
        if state.call_amount == 0:
            return self.bet_pot(state, 0.25) if equity > 0.5 else self.call()
        if equity > state.pot_odds + 0.05:
            return self.call()
        return self.check_or_fold(state)


class MinRaiser(Base):
    """Min-raises anything decent and rarely folds, which makes pots cheap to
    build and punishes folding to small raises."""

    def run(self, actions, state):
        strength = self.strength() if not state.board else self.equity(state)
        if strength > 0.55 and state.can_raise:
            return self.raise_to(state, state.min_raise_to)
        if state.call_amount == 0 or strength > state.pot_odds - 0.03:
            return self.call()
        return self.check_or_fold(state)


class Switcher(Base):
    """Plays tight for 60 hands and then turns into a maniac, to punish
    trusting old statistics."""

    def __init__(self, seed=0):
        super().__init__(seed)
        self.early = PushFold(seed)
        self.late = Maniac(seed)

    def seed(self, hand, player_id):
        super().seed(hand, player_id)
        self.current = self.early if self.hands_played <= 60 else self.late
        self.current.seed(hand, player_id)

    def run(self, actions, state):
        if self.hands_played <= 60 and not state.board:
            if self.strength() < 0.66:
                return self.check_or_fold(state)
        return self.current.run(actions, state)


class Adaptive(Base):
    """Learns how often we fold and attacks if we fold too much, otherwise it
    value-bets. It is what a good rival team could build."""

    def __init__(self, seed=0):
        super().__init__(seed)
        self.bets_made = 4.0
        self.folds_won = 2.0
        self.last_was_bet = False

    def run(self, actions, state):
        for action in actions:
            if action.player_id == 1 - self.player_id and action.kind == "fold":
                if self.last_was_bet:
                    self.folds_won += 1
        attack = self.folds_won / self.bets_made > 0.45
        move = self._choose(state, attack)
        self.last_was_bet = move.kind == "raise"
        if self.last_was_bet:
            self.bets_made += 1
        return move

    def end_game(self, actions, state):
        for action in actions:
            if action.player_id == 1 - self.player_id and action.kind == "fold":
                if self.last_was_bet:
                    self.folds_won += 1

    def _choose(self, state, attack):
        roll = self.rng.random()
        if not state.board:
            strength = self.strength()
            if state.current_bet <= state.big_blind:
                if strength > (0.36 if attack else 0.50):
                    return self.raise_to(state, 3 * state.big_blind)
                return self.call() if strength > 0.38 or state.call_amount == 0 else self.check_or_fold(state)
            if strength > 0.66:
                return self.raise_to(state, 3 * state.current_bet)
            if strength > 0.48 and state.pot_odds < 0.42:
                return self.call()
            return self.check_or_fold(state)
        equity = self.equity(state)
        if state.call_amount == 0:
            if equity > 0.65 or (attack and roll < 0.6):
                return self.bet_pot(state, 0.75)
            return self.call()
        if equity > 0.88:
            return self.bet_pot(state, 1.0)
        if equity > state.pot_odds + 0.08:
            return self.call()
        return self.check_or_fold(state)


class Mirror(Model):
    """Our own model, as a test for leaks that a copy of it can find."""

    def __init__(self, seed=0):
        super().__init__()
        self.rng = random.Random(seed)


class Previous(previous_model.Model):
    """A frozen earlier version: the new one has to beat it directly."""

    def __init__(self, seed=0):
        super().__init__()
        self.rng = random.Random(seed)


SPARRING = {
    "previous": Previous,
    "pushfold": PushFold,
    "balanced": Balanced,
    "maniac": Maniac,
    "trapper": Trapper,
    "polarized": Polarized,
    "minraiser": MinRaiser,
    "switcher": Switcher,
    "adaptive": Adaptive,
    "mirror": Mirror,
}
