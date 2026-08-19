# Simba Plays Kaggri

A reproducible research project for building, testing, and preserving autonomous
agents for Kaggle's **Kaggriculture** competition.

The default local entry point, [`main.py`](main.py), currently runs the
**unsubmitted resilient portfolio candidate**. The latest live Kaggle upload
remains stable strawberry champion v3, submission `55631403`.

> **Kaggle API snapshot (20 August 2026, 04:31 IST):** submission `55631403`
> had a rating of **841.7** with a **19-15** public record over 34 rated games.
> Ratings continue to move as Kaggle schedules matches. See the complete
> [submission ledger](docs/SUBMISSIONS.md).

## How the project works

The research loop is deliberately simple:

1. Study public replays and identify repeatable economic or routing patterns.
2. Recreate those patterns as local opponent agents in `candidates/`.
3. Test every candidate in both player seats over the same random seeds.
4. Promote a bot only when it improves win rate without introducing execution
   errors or unsafe end-game behavior.
5. Preserve every submitted archive and its observed score so an older bot can
   be restored exactly.

The competition result is decided by win, loss, or tie, so the evaluation tools
prioritize paired win rate over a few unusually large coin totals.

## Local promotion candidate

The candidate in [`candidates/resilient_portfolio.py`](candidates/resilient_portfolio.py):

- opens with 8 melon seeds, 7 wheat seeds, 1 goose, 2 cows, 2 sheep, and 9 hands;
- expands toward 75 tiles with demand-conditioned crops and livestock;
- scales beyond an eight-animal engine only for animal-consuming shops;
- adjusts wheat, strawberries, tomatoes, and carrots for town demand, feed
  needs, and visible opponent supply;
- can increase to 10 or 11 hands when farm workload requires it;
- preserves placed animals and productive crops as its targets change;
- batches sales and liquidates remaining value before the episode ends; and
- falls back to legal `PASS` actions in `main.py` if an unexpected live error occurs.

This strategy is the current hypothesis, not a solved policy. It beat the live
incumbent 28-4 in a 32-match paired local gate, but remained 0-20 against
non-reactive top-leader replay traces. The complete evidence and its limits are
recorded in the [34-match forensic and v7 promotion gate](docs/LIVE_SUBMISSION_55631403.md).

## Quick start

Requirements:

- Python 3.11-3.13 (Python 3.12 is the tested default)
- [`uv`](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/mayur-samrutwar/simbaplayskaggri.git
cd simbaplayskaggri
uv sync --python 3.12 --extra dev
uv run pytest
```

Dependencies are locked in [`uv.lock`](uv.lock), including
`kaggle-environments==1.32.7`.

## Evaluate agents locally

Run the local promotion candidate against Kaggle's starter agent:

```bash
uv run python -m eval.tournament \
  --candidate main.py \
  --opponent starter \
  --seeds 0:8
```

The runner plays both seats for every seed, so `0:8` produces 16 matches. It
reports wins, losses, ties, money, margins, execution errors, and unsold
inventory.

For strict fault detection, test the implementation directly. `main.py` catches
unexpected exceptions for live reliability, which can otherwise hide a policy
failure from the environment status:

```bash
uv run python -m eval.tournament \
  --candidate candidates/resilient_portfolio.py \
  --opponent starter \
  --seeds 0:8
```

Compare several strategies in one paired-seat league:

```bash
uv run python -m eval.league \
  --agent champion=main.py \
  --agent baseline=candidates/hybrid.py \
  --agent starter=starter \
  --seeds 0:8
```

## Build a submission archive

```bash
uv run python -m eval.bundle --output dist/submission.tar.gz
```

This command only builds a local archive. It does **not** upload to Kaggle or
consume a submission allowance. The archive contains `main.py` and the runtime
modules required by the promoted strategy.

## Repository map

| Path | Purpose |
|---|---|
| [`main.py`](main.py) | Kaggle entry point and safe live fallback |
| [`candidates/`](candidates/) | Promoted, historical, reconstructed, and counter-strategy agents |
| [`eval/`](eval/) | Paired tournaments, leagues, replay analysis, and bundle tooling |
| [`tests/`](tests/) | Environment-contract, policy, replay, bundle, and registry tests |
| [`docs/`](docs/) | Strategy research, replay findings, benchmarks, and live audits |
| [`submissions/`](submissions/) | Machine-readable score registry and byte-exact rollback archives |
| [`competition/`](competition/) | Competition reference material used by the project |

Some research documents describe earlier incumbents. The authoritative current
entry point is always `main.py`; the dated [submission ledger](docs/SUBMISSIONS.md)
records which strategy was actually uploaded.

## Recorded submissions

| Submission | Strategy | Rating snapshot | Public record | Role |
|---:|---|---:|---:|---|
| `55631403` | Stable strawberry champion v3 | **841.7** | **19-15-0** | Current rating leader |
| `55625688` | Replay-derived adaptive hybrid v2 | **800.0** | **17-15-0** | Established baseline |
| `55623462` | Diversified crop v1 | **662.2** | **13-12-0** | Historical fallback |

These values came from the Kaggle API at 04:31 IST on 20 August 2026 and can
change as Kaggle schedules more matches. Exact hashes, strategy descriptions,
episode evidence, and rollback instructions are maintained in
[`docs/SUBMISSIONS.md`](docs/SUBMISSIONS.md) and
[`submissions/registry.toml`](submissions/registry.toml).

## Safety and reproducibility

- No Kaggle or GitHub credential belongs in this repository.
- Keep `KAGGLE_API_TOKEN` in the process environment or Kaggle's protected
  client storage; never place it in source, logs, or committed configuration.
- Replays, generated bundles, virtual environments, and ad-hoc run outputs are
  ignored by Git.
- Exact historical upload archives are retained intentionally for reliable
  rollback.
- Local results are evidence, not a guarantee of leaderboard performance.
