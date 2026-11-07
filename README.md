# PokerBot

A Texas Hold'em poker bot in Python, built in phases. It plays in its own
engine and against other bots, not on real-money sites.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

On macOS or Linux, use `.venv/bin/python` instead.

## Usage

```python
from pokerbot import evaluate, hand_category, parse_cards

score = evaluate(parse_cards("As Ks Qs Js Ts 2d 3c"))
print(hand_category(score).name)  # STRAIGHT_FLUSH
```

A higher score is a stronger hand, and equal scores tie. `evaluate` accepts 5,
6 or 7 cards and uses the best five.

## Phases

1. Project scaffold, cards and hand evaluator (done)
2. Game engine: betting rounds, pots and showdown
3. Monte Carlo equity and baseline bots
4. Tournament harness: bot-vs-bot matches and win-rate stats
5. CFR on Kuhn and Leduc poker
6. Abstraction and Monte Carlo CFR for Hold'em
7. Opponent modeling and tuning
