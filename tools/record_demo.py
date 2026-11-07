"""Record real matches, with the bot's reasoning, for the demo page. Not submitted.

    python -m tools.record_demo

Plays each opponent once and writes demo/index.html from demo/template.html.
Matches are not picked for their results: they all use seed 0. The bot sits in
each seat in turn, so a viewer sees both, whereas a real match plays one seat
per rotation with a fresh model.
"""

import json
import random

from card_utils import RANKS, full_deck
from engine import play_hand
from game_state import GameState
from model import Model, _hand_name
from tools.spar import OPPONENTS

MATCHES = ["trapper", "maniac", "balanced"]
HANDS = 200
ORDER = RANKS[::-1]  # the range grid runs from aces to twos

COMBOS_IN_CELL = {"pair": 6, "suited": 4, "offsuit": 12}
RATES_TO_TRACK = {
    "fold_to_raise": ("versus_raise", 0),
    "fold_to_bet": ("versus_bet", 0),
    "fold_to_all_in": ("all_in_preflop", 0),
    "open_raise": ("open", 2),
    "postflop_bet": ("check_or_bet", 2),
}


def range_grid(combos):
    """How much of each starting hand is in the range, 0 to 9, as 169 digits
    with suited hands above the diagonal."""
    counts = {}
    for combo in combos:
        name = _hand_name(*combo)
        counts[name] = counts.get(name, 0) + 1
    digits = []
    for row, first in enumerate(ORDER):
        for column, second in enumerate(ORDER):
            if row == column:
                name, kind = first + second, "pair"
            elif column > row:
                name, kind = first + second + "s", "suited"
            else:
                name, kind = second + first + "o", "offsuit"
            share = counts.get(name, 0) / COMBOS_IN_CELL[kind]
            digits.append(str(min(9, round(share * 9))))
    return "".join(digits)


class Recording(Model):
    """The real model, noting what it worked out at each decision."""

    def __init__(self):
        super().__init__()
        self.decisions = []
        self.notes = {}

    def _simulate(self):
        outcomes = super()._simulate()
        self.notes["equity"] = sum(outcomes) / len(outcomes)
        self.notes["range_size"] = len(self.range)
        self.notes["grid"] = range_grid(self.range)
        return outcomes

    def _raise_value(self, state, total, team, equity, realized):
        value = super()._raise_value(state, total, team, equity, realized)
        self.notes["raises"].append([total, round(value, 1)])
        self.notes["realized"] = realized
        return value

    def _decide(self, state):
        self.notes = {"raises": []}
        me = self.player_id
        pot, to_call, button = state.pot, state.call_amount, state.button
        stack = state.stacks[me]
        move = super()._decide(state)
        notes = self.notes
        if "equity" not in notes:
            notes.update(equity=None, range_size=len(self.range), grid="")
        call_value = None
        if notes["equity"] is not None:
            # The same sum the model does, which it does not keep.
            if not self.board or len(self.board) < 5:
                in_position = me == button
                realized = 0.98 if in_position else 0.88
            else:
                realized = 1.0
            if to_call >= stack:
                realized = 1.0
            call_value = notes["equity"] * realized * (pot + to_call) - to_call
            if move.kind == "call":
                assert abs(call_value - self.last_estimate) < 1e-6, (
                    call_value, self.last_estimate)
        self.decisions.append({
            "equity": notes["equity"] and round(notes["equity"], 3),
            "range_size": notes["range_size"],
            "grid": notes["grid"],
            "call_value": None if call_value is None else round(call_value, 1),
            "raises": notes["raises"],
            "to_call": to_call,
            "chose": move.kind,
            "amount": move.amount,
        })
        return move


def describe_hand(number, result, button, me, decisions, snapshot):
    """Every step of a hand, with chip counts from the engine's own rules."""
    state = GameState([500, 500])
    state.setup_hand([500, 500], button, 10, 20, ["us", "them"])
    pending = list(decisions)
    steps = []
    shown = []
    for action in result.actions:
        step = {
            "who": "dealer" if action.player_id == -1
            else "us" if action.player_id == me else "them",
            "kind": action.kind,
        }
        if action.kind in ("raise", "win"):
            step["amount"] = action.amount
        if action.kind == "reveal_card":
            if action.player_id == -1:
                step["card"] = str(action.card)
            else:
                if action.player_id != me:
                    shown.append(str(action.card))
                continue
        if action.kind == "call":
            step["amount"] = state.call_amount
        if action.player_id == me and action.kind in ("fold", "call", "raise"):
            step["decision"] = pending.pop(0)
        state.process_action(action)
        step["pot"] = state.pot
        step["stacks"] = [state.stacks[me], state.stacks[1 - me]]
        steps.append(step)
    assert not pending, "a decision did not reach the table"
    return {
        "n": number,
        "seat": "button" if button == me else "big blind",
        "ours": [str(card) for card in result.hands[me]],
        "theirs": shown,
        "net": result.net[me],
        "steps": steps,
        "tags": hand_tags(result, me, decisions),
        "reads": snapshot,
    }


def hand_tags(result, me, decisions):
    """Labels for hands worth showing, set by rule and not chosen by hand."""
    tags = []
    last = decisions[-1] if decisions else None
    they_folded = result.actions and any(
        action.kind == "fold" and action.player_id != me
        for action in result.actions
    )
    if (
        they_folded and last and last["chose"] == "raise"
        and last["equity"] is not None and last["equity"] < 0.4
    ):
        tags.append("bluff")
    if any(
        action.kind == "fold" and action.player_id == me
        for action in result.actions
    ) and last and last["to_call"] >= 100:
        tags.append("big fold")
    return tags


def play_match(name, seed):
    ours, theirs = Recording(), OPPONENTS[name](seed=seed)
    ours.rng = random.Random(f"ours:{seed}")
    hands = []
    running = 0
    timeline = []
    for number in range(HANDS):
        deck = full_deck()
        random.Random(f"{seed}:{number}").shuffle(deck)
        button = number % 2
        ours.decisions = []
        result = play_hand(
            [ours, theirs], deck, [500, 500], button, 10, 20, ["us", "them"]
        )
        assert result.faults == {}, result.faults
        running += result.net[0]
        reads = {
            key: round(ours._rates("them", point)[index], 3)
            for key, (point, index) in RATES_TO_TRACK.items()
        }
        reads["bluffs"] = round(ours._read(
            "them", ("bluffs",), ("bluffs", "value_bets"), (0.2, 6)
        ), 3)
        hands.append(describe_hand(
            number + 1, result, button, 0, ours.decisions, reads
        ))
        timeline.append(running)
    return {
        "name": name,
        "hands": hands,
        "running": timeline,
        "bb_per_100": round(100 * running / 20 / HANDS, 1),
    }


def main():
    data = {
        "ranks": ORDER,
        "matches": [play_match(name, 0) for name in MATCHES],
    }
    with open("demo/template.html", encoding="utf-8") as file:
        template = file.read()
    text = json.dumps(data, separators=(",", ":"))
    with open("demo/index.html", "w", encoding="utf-8") as file:
        file.write(template.replace("/*DATA*/null", text))
    for match in data["matches"]:
        bluffs = sum("bluff" in hand["tags"] for hand in match["hands"])
        folds = sum("big fold" in hand["tags"] for hand in match["hands"])
        print(f"{match['name']:<10} {match['bb_per_100']:>+8.1f} bb/100  "
              f"bluffs {bluffs}  big folds {folds}")
    print(f"demo/index.html: {len(text) // 1024} KB of data")


if __name__ == "__main__":
    main()
