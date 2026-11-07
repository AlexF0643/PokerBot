import random

import pytest

from arena.dummies import DUMMIES
from card_utils import full_deck
from engine import play_hand
from model import Model, _hand_name


class StrictModel(Model):
    """Model without its safety net, so that bugs fail these tests."""

    def run(self, actions, game_state):
        self._observe(actions, game_state, True)
        return self._decide(game_state)

    def end_game(self, actions, game_state):
        self._observe(actions, game_state, False)


def play(model, opponent, hands, stack=500):
    rng = random.Random(5)
    total = 0
    for hand in range(hands):
        deck = full_deck()
        rng.shuffle(deck)
        button = hand % 2
        result = play_hand(
            [model, opponent], deck, [stack, stack], button, 10, 20,
            ["us", "them"],
        )
        assert result.faults == {}
        total += result.net[0]
    return total


@pytest.mark.parametrize("name", list(DUMMIES))
def test_decisions_raise_no_errors(name):
    play(StrictModel(), DUMMIES[name](seed=1), 40)


def test_no_errors_with_short_stacks():
    play(StrictModel(), DUMMIES["random"](seed=1), 40, stack=45)


def test_learns_that_a_shover_always_shoves():
    model = StrictModel()
    play(model, DUMMIES["shove"](seed=1), 30)
    points = model.stats["them"]
    assert model._rates("them", "open")[3] > 0.5
    assert all(counts[0] == 0 for counts in points.values())


def test_takes_the_blinds_from_a_folder():
    model = StrictModel()
    assert play(model, DUMMIES["fold"](seed=1), 60) > 0
    assert model._rates("them", "versus_raise")[0] > 0.7


def test_tracks_answers_to_all_ins_separately():
    model = StrictModel()
    play(model, DUMMIES["call"](seed=1), 60)
    points = model.stats["them"]
    counts = [points.get(name, (0, 0)) for name in
              ("all_in_preflop", "all_in_postflop")]
    assert sum(count[1] for count in counts) > 0
    assert all(count[0] == 0 for count in counts)


def test_range_narrows_after_a_raise():
    model = StrictModel()
    model.seed([], 0)
    size = len(model.range)
    model._narrow_range("them", "open", "shove")
    assert 8 <= len(model.range) < size
    # The strongest hands stay.
    assert _hand_name(*model.range[-1]) == "AA"
