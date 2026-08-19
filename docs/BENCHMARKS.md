# Local benchmark record

> **Live correction (2026-08-20):** the 89.8% figure below did not transfer to
> Kaggle. Submission 55625688 is 14-13 over 27 public games, with a 795.3 rating
> at the audit refresh. The candidate's local mean cash was realistic, but the
> replay-derived opponents were too weak and shared the candidate's scheduler.
> See [the complete live submission audit](LIVE_SUBMISSION_AUDIT.md). Treat the
> historical figures below as emulator regression tests, not promotion proof.

Environment: `kaggle-environments==1.32.7`, Python 3.12, full 720-step games,
fixed seeds, both player seats.

## Current promotion: adaptive five-animal hybrid

The promoted agent opens with two cows, three sheep, ten wheat seeds and three
strawberry seeds, then chooses crops from live prices, shop demand, and visible
opponent supply. It retains a 15-animal cap, uses 75 tiles by default, avoids
feed buy/sell churn, waters one-time crops through their final bonus day, and
fully liquidates on day 29.

The final selection used development seeds only for tuning. Untouched paired-
seat holdouts produced:

| Candidate | Opponent | Seeds | W-L-T | Mean margin |
|---|---|---:|---:|---:|
| final hybrid | Arman-derived | 4–11 | 15-1-0 | +19,459 |
| final hybrid | tetsuya-derived | 4–11 | 13-3-0 | +5,155 |
| final hybrid | common 2C/2S family | 4–11 | 13-3-0 | +12,662 |
| final hybrid | residual counter | 4–11 | 14-2-0 | +1,717 |
| final hybrid | Arman-derived | 12–19 | 16-0-0 | +17,445 |
| final hybrid | tetsuya-derived | 12–19 | 14-2-0 | +6,228 |
| final hybrid | common 2C/2S family | 12–19 | 14-2-0 | +17,545 |
| final hybrid | residual counter | 12–19 | 13-3-0 | +3,713 |
| final hybrid | livestock | 12–19 | 16-0-0 | +48,874 |
| final hybrid | anti-melon | 12–19 | 14-2-0 | +22,185 |
| final hybrid | adaptive crop opening | 12–19 | 16-0-0 | +23,542 |

Combined untouched holdouts: **158-18-0 (89.8%)** across 176 full games.
Every run completed with zero agent errors, zero terminal shed units, and zero
terminal carried units. Four paired self-play seeds produced 4-4 with exactly
zero aggregate margin, confirming the seat-swap accounting.

These opponents are replay-derived emulators, not the private leaderboard
source code; the figures measure robustness to the observed strategy families,
not a guaranteed live rating.

### Initial live check

Kaggle accepted submission **55625688** and ran validation episode 94540309
to completion. Its first public episode, 94540866, beat Hubbahub
**104,441–62,373** (+42,068). Immediately after that one rated match the new
submission showed **698.4**, above the previous submission's 645.1. This is an
initial, highly provisional rating; continued matchmaking is authoritative.

## Historical crop-only promotion

The first incumbent used 25 opening melons. A bounded search found that 16
melons + 9 wheat with 7 hands consistently countered the monoculture without
sacrificing the livestock matchup. That diversified opener is now `main.py`.

| Candidate | Opponent | Seeds | W-L-T | Mean margin | Terminal stock |
|---|---|---:|---:|---:|---:|
| diversified crop | 25-melon monoculture | 4–7 | 8-0-0 | +13,469 | 0 |
| diversified crop | 25-melon monoculture | 8–9 holdout | 4-0-0 | +14,174 | 0 |
| diversified crop | livestock | 4–7 | 6-2-0 | +13,005 | 0 |
| diversified crop | livestock | 8–9 holdout | 4-0-0 | +20,826 | 0 |
| diversified crop | anti-melon mix | 8–9 holdout | 2-2-0 | +100 | 0 |
| diversified crop | starter | 8–9 holdout | 4-0-0 | +64,790 | 0 |

The anti-melon mix is a useful close adversary rather than a demonstrated
improvement: the paired result was 2–2 and essentially even on margin. It stays
in the league.

## Earlier strategy trials

| Candidate | Opponent | Seeds | W-L-T | Mean candidate cash | Mean margin |
|---|---|---:|---:|---:|---:|
| original 25-melon crop | starter | 0–7 | 16-0-0 | 77,814 | +74,230 |
| original 25-melon crop | mixed livestock | 0–3 | 8-0-0 | 69,632 | +13,685 |
| mixed livestock (14 goose/2 cow/2 sheep) | starter | 0–2 | 6-0-0 | 56,939 | +53,439 |

The 25-melon headline cash was misleading in mirrors: the shared quadratic
melon curve collapses, and the diversified policy wins the paired head-to-head.

## Reliability gates

- strict candidate and black-box `main.py` paths complete without agent errors
- exact last callable and final actionable step are contract-tested
- final harvest cutoff leaves zero shed/carried units in promotion runs
- local archive is loaded from an isolated directory in tests
- source credential scan is clean
- current suite: 19 tests passing

These samples establish a credible local incumbent, not statistical proof of a
competition win. Live opponents remain private and can adapt.
