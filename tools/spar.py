"""Measure the model against tools/sparring.py. Not part of the submission.

    python -m tools.spar --deals 200 --seeds 8

Plays the real format: every deck once in each seat, with fresh models per
rotation and 500-chip stacks that reset every hand. It runs in-process for
speed, so timeouts are not enforced; python -m evals plays the real workers.
"""

import argparse
import math
import multiprocessing
import random

import model as model_module
from arena.dummies import DUMMIES
from card_utils import full_deck
from engine import play_hand
from model import Model
from tools.sparring import SPARRING

OPPONENTS = {**SPARRING, "tight": DUMMIES["tight"], "equity": DUMMIES["equity"]}


def play_match(task):
    """Our big blinds won per hand, one value for each deck."""
    name, seed, deals, overrides = task
    for constant, value in overrides.items():
        setattr(model_module, constant, value)
    values = [0.0] * deals
    faults = 0
    for rotation in range(2):
        ours = Model()
        ours.rng = random.Random(f"ours:{seed}")
        theirs = OPPONENTS[name](seed=seed)
        us_first = rotation == 0
        models = [ours, theirs] if us_first else [theirs, ours]
        teams = ["us", name] if us_first else [name, "us"]
        for deal in range(deals):
            deck = full_deck()
            random.Random(f"{seed}:{deal}").shuffle(deck)
            result = play_hand(models, deck, [500, 500], 0, 10, 20, teams)
            seat = 0 if us_first else 1
            values[deal] += result.net[seat] / 40
            faults += seat in result.faults
    return name, seed, values, faults


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deals", type=int, default=200)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--opponents", nargs="+", default=list(OPPONENTS))
    parser.add_argument(
        "--set", nargs="*", default=[], metavar="NAME=VALUE",
        help="try a different value for a constant in model.py",
    )
    args = parser.parse_args()
    overrides = {
        constant: float(value)
        for constant, value in (item.split("=") for item in args.set)
    }

    tasks = [
        (name, seed, args.deals, overrides)
        for name in args.opponents
        for seed in range(args.seeds)
    ]
    results = {name: [] for name in args.opponents}
    faults = dict.fromkeys(args.opponents, 0)
    with multiprocessing.Pool() as pool:
        for name, _, values, count in pool.imap_unordered(play_match, tasks):
            results[name].append(values)
            faults[name] += count

    print(f"settings: {args.set or 'as in model.py'}")
    print(f"{'opponent':<12}{'bb/100':>10}{'95% CI':>9}"
          f"{'worst':>9}{'best':>9}{'faults':>8}")
    overall = []
    for name in args.opponents:
        values = [value for match in results[name] for value in match]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        interval = 1.96 * math.sqrt(variance / len(values))
        per_match = [100 * sum(match) / len(match) for match in results[name]]
        overall.append(100 * mean)
        print(f"{name:<12}{100 * mean:>+10.1f}{100 * interval:>9.1f}"
              f"{min(per_match):>+9.0f}{max(per_match):>+9.0f}"
              f"{faults[name]:>8}")
    print(f"{'average':<12}{sum(overall) / len(overall):>+10.1f}")


if __name__ == "__main__":
    main()
