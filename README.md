# simbaplayskaggri

Local research project for the Kaggle **Kaggriculture** autonomous-agent
competition. Evaluation, replay analysis, and bundle construction are local;
uploading remains a separate, explicit Kaggle CLI action.

## Setup

```bash
UV_CACHE_DIR=/private/tmp/simbaplayskaggri-uv-cache uv venv --python 3.12
UV_CACHE_DIR=/private/tmp/simbaplayskaggri-uv-cache uv sync --extra dev
```

The environment is pinned to `kaggle-environments==1.32.7`, the version used
for the initial benchmark on 2026-08-19.

## Local checks

```bash
.venv/bin/pytest
.venv/bin/python -m eval.tournament --candidate main.py --opponent starter --seeds 0:8
.venv/bin/python -m eval.league \
  --agent final=main.py \
  --agent arman=candidates/leaderboard_arman.py \
  --agent common=candidates/leaderboard_common.py \
  --seeds 0:8
```

The tournament runner tests both player seats for every seed and reports win
rate first because the live competition rating only depends on win/loss/tie,
not victory margin.

For strict local fault detection, benchmark
`candidates/champion_strawberry.py` directly. `main.py` intentionally catches
unexpected exceptions and returns safe PASS actions for live reliability,
which can otherwise hide a policy exception from the environment's status
field.

Official competition references are in [`competition/`](competition/). Cached
public replays belong in `replays/`, and local tournament outputs in `runs/`;
both are ignored by Git. The replay audit and counter-strategy findings are in
[`docs/LEADERBOARD_ANALYSIS.md`](docs/LEADERBOARD_ANALYSIS.md).

The live score chart, exact strategy history, and byte-exact rollback archives
for every submission are tracked in
[`docs/SUBMISSIONS.md`](docs/SUBMISSIONS.md). Update that ledger after every
live score check and preserve each future uploaded artifact before iterating.

To verify the same multi-file layout Kaggle would load, build a local bundle:

```bash
.venv/bin/python -m eval.bundle --output dist/submission.tar.gz
```

This only creates an archive. It does not upload or submit anything. The
archive contains the promoted occupied-position-stable strawberry policy and
all of its runtime dependencies.

## Safety

- No API token is stored by this project.
- Never add credentials to `.env`, source code, logs, or commits.
- No submission command is included in the evaluation workflow.
- Rotate any token pasted into chat or another logged surface before using it
  for long-term access.
