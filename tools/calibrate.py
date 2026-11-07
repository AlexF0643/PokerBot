"""Compare what the model predicts with what it wins. Not submitted.

    python -m tools.calibrate balanced --deals 200 --seeds 8

For each kind of decision, prints the chips back the model expected and the
chips back it really got, from that decision on. A large gap is a wrong
estimate, and the place to look for a leak.
"""

import argparse
import math
import multiprocessing
import random
from collections import defaultdict

from card_utils import full_deck
from engine import play_hand
from model import Model
from tools.spar import OPPONENTS

STREETS = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}


class Recording(Model):
    def __init__(self):
        super().__init__()
        self.pending = []
        self.finished = []

    def _decide(self, state):
        chips_in = 500 - state.stacks[self.player_id]
        move = super()._decide(state)
        kind = move.kind
        if kind == "raise" and self.we_shoved:
            kind = "shove"
        elif kind == "call" and state.call_amount == 0:
            kind = "check"
        self.pending.append(
            (STREETS[len(self.board)], kind, self.last_estimate, chips_in)
        )
        return move


def play(task):
    name, seed, deals = task
    records = []
    for rotation in range(2):
        ours, theirs = Recording(), OPPONENTS[name](seed=seed)
        ours.rng = random.Random(f"ours:{seed}")
        models = [ours, theirs] if rotation == 0 else [theirs, ours]
        teams = ["us", name] if rotation == 0 else [name, "us"]
        for deal in range(deals):
            deck = full_deck()
            random.Random(f"{seed}:{deal}").shuffle(deck)
            ours.pending = []
            result = play_hand(models, deck, [500, 500], 0, 10, 20, teams)
            net = result.net[rotation]
            for street, kind, estimate, chips_in in ours.pending:
                records.append((street, kind, estimate, net + chips_in))
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("opponent")
    parser.add_argument("--deals", type=int, default=200)
    parser.add_argument("--seeds", type=int, default=8)
    args = parser.parse_args()
    tasks = [(args.opponent, seed, args.deals) for seed in range(args.seeds)]
    buckets = defaultdict(list)
    with multiprocessing.Pool() as pool:
        for records in pool.imap_unordered(play, tasks):
            for street, kind, estimate, real in records:
                buckets[street, kind].append((estimate, real))
    print(f"{args.opponent}\n{'decision':<18}{'count':>6}{'predicted':>11}"
          f"{'real':>9}{'+/-':>7}{'gap chips':>11}")
    for street in STREETS.values():
        for kind in ("fold", "check", "call", "raise", "shove"):
            rows = buckets.get((street, kind))
            if not rows:
                continue
            count = len(rows)
            predicted = sum(row[0] for row in rows) / count
            real = sum(row[1] for row in rows) / count
            spread = sum((row[1] - real) ** 2 for row in rows) / max(1, count - 1)
            interval = 1.96 * math.sqrt(spread / count)
            print(f"{street + ' ' + kind:<18}{count:>6}{predicted:>11.1f}"
                  f"{real:>9.1f}{interval:>7.1f}"
                  f"{(real - predicted) * count:>+11.0f}")


if __name__ == "__main__":
    main()
