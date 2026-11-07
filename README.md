# Ineffective Altruists Pokerbot

Our entry for the Pokerbot Challenge at GreatUniHack 2026, run by MUDS AI: a
Python bot for heads-up no-limit Texas hold'em. It only plays in this
competition's engine and against other bots, not on real-money sites.

The organisers' original instructions follow our notes, from
[Poker bot hackathon](#poker-bot-hackathon) onwards.

## The competition

- Every bot plays every other bot heads-up, and the best overall bb/100 (big
  blinds won per 100 hands) wins.
- Every hand starts with 500 chips and 10/20 blinds, so 25 big blinds deep.
- Each deck is played from both seats. The bot is rebuilt from its pickle for
  each seat rotation, so it forgets what it learned between them.
- Each move has a 10 second limit. A crash, timeout or illegal move is a fault,
  and a bot that times out is out for the rest of that match.

## How the bot plays

At each decision, the bot estimates how many chips it would get back from
folding, calling and several raise sizes, then picks the best. A raise has to
beat the safer option by a margin that grows with its size. It also won't raise
all-in with under 30% equity against the hands it expects to call.

1. **Simulation:** it plays the hand out 600 times against the hands the
   opponent could hold. On the river it checks each of those hands once.
2. **Learning rates:** it counts how each opponent folds, calls, raises and
   shoves in each situation, starting from assumed rates that count for 14 hands.
3. **Narrowing the range:** it uses those rates to narrow down what the
   opponent holds after each move.
4. **Learning from showdowns:** it uses revealed cards to judge how often that
   opponent bluffs and slow-plays.

Any internal error falls back to a legal check or fold, so an error can't cause
a fault. The test suite runs the bot without this fallback, so bugs still show.

Strong poker research systems such as Libratus, Pluribus and DeepStack need far
more computing power than a one-day event allows. This bot aims to exploit the
habits of the bots it meets, and it doesn't try to play a near-perfect strategy.

## Files

Uploaded with the submission:

| File | What it is |
|---|---|
| `model.py` | The bot |
| `fast_eval.py` | A hand evaluator about 45 times faster than the engine's |
| `preflop_table.py` | Each starting hand's equity against a random hand |

Our tools, which aren't uploaded:

| File | What it does |
|---|---|
| `tools/sparring.py` | Nine practice bots in different styles |
| `tools/spar.py` | Plays the bot against the practice bots in the real format |
| `tools/calibrate.py` | Compares the value the bot predicts with what it wins |
| `tools/record_demo.py` | Records matches and builds the demo page |
| `tools/build_preflop_table.py` | Regenerates `preflop_table.py` |
| `tools/previous_model.py` | A frozen earlier version of the bot to play against |

## Testing the bot

Run these from the repo root. On macOS or Linux, use `.venv/bin/python`.

```sh
# Is it a valid submission?
.venv\Scripts\python -m pytest tests/test_model.py -q

# Would the organisers accept it?
.venv\Scripts\python -m submit --team ineffective-altruists

# How does it do against the organisers' dummy bots?
.venv\Scripts\python -m evals

# How does it do against the tougher practice bots?
.venv\Scripts\python -m tools.spar --deals 200 --seeds 8

# How does it do against another team's bot? Their .py files must be importable.
.venv\Scripts\python -m evals --opponents path\to\their_bot.pkl --deals 1000

# Where is it leaking chips?
.venv\Scripts\python -m tools.calibrate balanced --seeds 8
```

Trust a result only when its margin doesn't include 0.

## Results

These come from bots we wrote or the organisers' simple dummies, and we tuned
against the practice bots, so they probably flatter the bot. They don't predict
a tournament result.

Against the practice bots and `tight`, over 16 matches of 200 deals per opponent:

| Opponent | Style | bb/100 | 95% margin |
|---|---|---:|---:|
| `minraiser` | Min-raises and rarely folds | +191.5 | 22.0 |
| `maniac` | Constant large bluffs | +163.9 | 26.0 |
| `trapper` | Slow-plays strong hands, bets weak ones | +154.3 | 19.5 |
| `polarized` | Small bets with medium hands, shoves with its best and air | +136.6 | 21.2 |
| `switcher` | Tight for 60 hands, then a maniac | +106.5 | 22.6 |
| `adaptive` | Learns how often we fold and attacks it | +49.4 | 15.6 |
| `pushfold` | Shoves or folds preflop | +43.6 | 10.4 |
| `tight` | Organiser dummy that plays strong hands only | +40.8 | 8.1 |
| `balanced` | Sound ranges with steady bluffs | +36.3 | 14.9 |
| `previous` | Our earlier version | -1.5 | 17.9 |
| **Average** | | **+92.1** | |

Against the organisers' dummies, using `python -m evals --deals 300` (600 hands
each, with no faults):

| Opponent | bb/100 | 95% margin |
|---|---:|---:|
| `call` | +544.2 | 72.6 |
| `random` | +315.6 | 89.4 |
| `shove` | +254.2 | 94.5 |
| `equity` | +187.5 | 60.4 |
| `fold` | +74.7 | 0.7 |
| `tight` | +42.4 | 25.7 |

Known weaknesses:

- Earlier versions overrated postflop raises. For example, flop shoves against
  `balanced` were predicted at 147 chips and returned about 72. We haven't
  re-measured this since adding the all-in rule.
- It is level with its own earlier version, and only modestly ahead of `balanced`.
- The all-in rule costs chips against bots that raise at random: `random` fell
  from +392 (8 matches) to +318 (16 matches). We accepted this because the rule
  protects against selective callers like `balanced`.
- Overall strength barely changed in the last two rounds of tuning. The average
  went from +85.4 to +91.0 and then +92.1, too small a gain to prove statistically.

## Demo

Open `demo/index.html` in a browser. It replays real recorded hands and shows
what the bot worked out before each move: its chance of winning, the chips it
expected back from each option, the opponent's likely hands and what it had
learned so far. Use **Next step** or the arrow keys to move through a hand, or
**Play** to run hands automatically.

The recorded matches all use one fixed seed and weren't chosen for their results:
`trapper` +86.0, `maniac` +135.5 and `balanced` +3.0 bb/100. One match says little
about strength. The bot swaps seats every hand in these recordings so viewers see
both seats, whereas real matches play one seat per rotation.

To rebuild the page after changing the bot:

```sh
.venv\Scripts\python -m tools.record_demo
```

## Submitting

The form opens at 16:00 and closes at 18:00 on 7 November 2026, and the newest
upload that works is the one that plays.

```sh
.venv\Scripts\python -m submit --team ineffective-altruists
```

Upload `ineffective-altruists.pkl`, `model.py`, `fast_eval.py` and
`preflop_table.py`.

---

# Poker bot hackathon

Write a bot that plays no-limit Texas hold'em. Your bot is a `Model` in
`model.py`. It is pickled and submitted, and the organisers' engine plays it
against other teams' bots.

**Join the participants' WhatsApp group** for announcements and questions: https://tr.ee/5W_MS_DJK9

## 1. Fork and set up

1. **Fork the repo.** Fork https://github.com/Manchester-AI-Society/poker_bot
   on GitHub (your own copy, under your account) and clone **your fork**. Do
   not clone the original: you would have nowhere to keep your work.
2. Create a virtual environment and install the dependencies (Python 3.10+;
   Windows, macOS and Linux all work):

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt          # Windows: .venv\Scripts\pip ...
```

Run everything with the venv's Python from the repo root: `.venv/bin/python`
(Windows: `.venv\Scripts\python`). In VS Code, select `.venv` as the
interpreter. If `venv` is missing on Ubuntu:
`sudo apt install python3-venv python3-pip`. The commands below say
`.venv/bin/python`; on Windows read it as `.venv\Scripts\python`.

## 2. Implement `model.py`

**`model.py` is the one file you must implement.** Add your own files next to
it if you need them. The template calls every hand, so fill in:

- `seed(hand, player_id)`: your two hole cards and your seat, once per hand.
  Store them.
- `run(actions, game_state)`: on each of your turns, return one
  `PlayerAction`: `fold`, `call` (also checks) or `raise_to`.
- `end_game(actions, game_state)` (optional): called after every hand. Learn
  from it, for example about opponents, using `game_state.teams`.

Rules that matter:

- Keep the model's attributes plain data (numbers, lists, dicts, numpy
  arrays, weights). No lambdas, open files, sockets or threads: the model is
  pickled. Load weights and data in `__init__`.
- Do not edit `card_utils.py`, `player_action.py`, `game_state.py` or
  `game_interface.py`. The organisers' copies are what play.
- Only use `GameStateView` names listed in [CLAUDE.md](CLAUDE.md): any other
  name raises `AttributeError`.

[CLAUDE.md](CLAUDE.md) has the full rules, the API tables and the common
mistakes. Read it before you start.

## 3. Check and measure your bot

```sh
# Is it a valid submission? (pickles, plays legally, no faults, in time)
.venv/bin/python -m pytest tests/test_model.py -q

# How strong is it? bb/100 against each dummy bot, with a 95% interval
.venv/bin/python -m evals
.venv/bin/python -m evals --opponents tight equity --deals 1000 --table
```

Beating the dummy bots shows your bot works, not that it will win the
tournament: that depends on the other teams. Results are only meaningful when
the interval does not include 0, so add `--deals` to narrow it.

## 4. Submit

Your bot is submitted as a **pickle plus the code it came from**, so the
organisers can read the code before anything runs. From the repo root:

```sh
.venv/bin/python -m submit --team myteam
```

This does `pickle.dump(Model(), ...)` into `myteam.pkl` and then checks it
the way the organisers will: it lists the files you must upload, shows
anything the code review will flag, and plays your model from a clean copy of
just those files against the dummy bots. Fix anything it reports, then upload
**every file it lists** (`myteam.pkl` and your `.py` files) in the submission
form. The form opens at 16:00 and its link appears then on the event
website (until then submissions are closed); the deadline is 18:00. Submit
again before the deadline if
you improve it: the newest upload that works is the one that plays.

What the review looks for:

- **The pickle** may only name your own modules and plain data (numbers,
  lists, dicts, sets, numpy arrays, `Card`, `PlayerAction`). A pickle that
  names anything else, such as `os.system`, is refused and never run.
- **Your `.py` files** are read for imports such as `os`, `subprocess` or
  `socket`, for `eval`/`exec`/`open`, and for reaching into the engine's
  internals (`_state`, `__globals__`, `_getframe`). A flagged file waits for
  an organiser to read it, so keep your code plain: no network, no files, no
  tricks.
- Keep your files flat next to `model.py` (no folders), named with letters,
  digits and `_`, and not like a standard library module (`random.py`).
- Put weights and data inside the model object (load them in `__init__`);
  files on disk are not available when your bot plays.

## For the organiser

Everything is under `event/` (`--root` to change it). Python 3.10+ on Windows,
macOS or Linux.

```sh
.venv/bin/python -m arena.event import DOWNLOADS   # the form's downloads
.venv/bin/python -m arena.event status             # who is ready / waiting
.venv/bin/python -m arena.event review TEAM        # findings, then the code
.venv/bin/python -m arena.event approve TEAM       # after reading it
.venv/bin/python -m arena.event run --deals 200    # every bot plays every other
.venv/bin/python -m arena.event export --out site_out --delay 120 --spacing 20 --loop 30
```

`import` reads either one folder per team or the flat folder Google Forms
makes (files named `<file> - <respondent>`, one respondent's files belong
together; a team's name is its `.pkl` name). Each upload is vetted
(`arena/vet.py`) before its code runs: a pickle naming anything but the team's
own modules and plain data is `REFUSED`; a team whose code has flagged lines
(or every team, with `--review-all`) is `NEEDS_REVIEW` until you have read it
with `review` and run `approve`; the rest are played against dummy bots and
become `READY`. A newer upload that fails never replaces one that works.

`run` plays one round: every ready team against every other, heads-up, each
pairing as duplicate deals (seats swapped), so card luck mostly cancels; the
best bb/100 is the champion. It saves every hand, can be stopped and started
again (finished pairings are skipped), and `--concurrency` sets how many
pairings play at once.

`export` writes the results site (the organiser's pages, kept outside this
repository in `site/`, plus `data/`). With
`--delay` and `--spacing` each finished pairing is shown (with a replay of its
biggest hands) some time after it ended and at least that far after the
previous one, so the site feels live but runs behind; standings are computed
from what is shown and the champion appears with the last pairing. `--loop`
keeps exporting; `--git-push` commits and pushes the folder (a git clone that
a static host serves). The Home page text is `event.json`.

Unpickling runs the team's code. Vetting keeps out the obvious attacks and
shows you the code, but it is not a sandbox: for real isolation run the
workers under `--launcher` (for example `bwrap` on Linux, or a container or
VM), on a machine you can spare.
