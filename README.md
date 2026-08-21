# Simba Plays Kaggri

A reproducible research project for building, testing, and preserving autonomous
agents for Kaggle's **Kaggriculture** competition.

The default local entry point, [`main.py`](main.py), currently runs the
**unsubmitted v10 throughput refinement**. Latest live upload is throughput v8,
submission `55654212`.

> **Kaggle API snapshot (21 August 2026, 13:51 IST):** submission `55654212`
> had a rating of **843.7** with a **22-16** public record over 38 rated games.
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

The candidate in [`candidates/throughput_portfolio.py`](candidates/throughput_portfolio.py):

- opens with 8 melon seeds, 7 wheat seeds, 2 cows, 2 sheep, and 9 hands;
- expands toward 75 tiles with demand-conditioned crops and livestock;
- scales by two animals per relevant shop, up to a 20-animal calendar cap;
- rotates up to six uncommitted tomato/carrot cells into demanded strawberries;
- fills at most three otherwise-idle cells with recurring feed wheat;
- adjusts wheat, strawberries, tomatoes, and carrots for town demand, feed
  needs, and visible opponent supply;
- hires a twelfth hand only for real backlog in a diverse town;
- preserves placed animals and productive crops as its targets change;
- batches sales and liquidates remaining value before the episode ends; and
- falls back to legal `PASS` actions in `main.py` if an unexpected live error occurs.

This remains a hypothesis. Across all 37 v8 live traces, isolated v9 and v10
both went 25-12; v10 raised mean cash by 250 and margin by 422. Against 20
top-player traces it retained 2-18 while improving cash by 518 and margin by
489. It beat isolated v9 **32-16-8** across 56 fixed-shop games at +1,384 mean
margin. A 32-match randomized head-to-head was nearly neutral at -37 mean
margin, with zero errors or terminal stock. No score is guaranteed.

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
  --candidate candidates/throughput_portfolio.py \
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
| `55654212` | Replay-audited throughput v8 | **843.7** | **22-16-0** | Current rating leader |
| `55631403` | Stable strawberry champion v3 | **832.7** | **24-26-0** | Historical fallback |
| `55625688` | Replay-derived adaptive hybrid v2 | **767.7** | **17-15-0** | Established baseline |
| `55623462` | Diversified crop v1 | **662.2** | **13-12-0** | Historical fallback |

These values came from the Kaggle API at 13:51 IST on 21 August 2026 and can
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
