# Submission 55631403: 34-match forensic and v7 promotion gate

This audit separates facts returned by Kaggle from local counterfactual tests.
It does not treat a local replay result as a promised leaderboard rating.

## Official Kaggle snapshot

The read-only Kaggle API snapshot at `2026-08-19T23:01:44.559417+00:00`
reported:

| Submission | Rating | Rated matches | Wins | Losses | Win rate |
|---:|---:|---:|---:|---:|---:|
| `55631403` | **841.7** | **34** | **19** | **15** | **55.88%** |

Validation episode `94647666` is excluded. The replay directory contains all
34 rated episodes plus that one validation episode, and every extracted final
score agrees with Kaggle's recorded reward.

## Why the incumbent wins and loses

| Metric, mean per game | In 19 wins | In 15 losses |
|---|---:|---:|
| Our final score | 87,429 | 83,059 |
| Opponent final score | 71,388 | 102,480 |
| Our late productive cash | 60,188 | 54,470 |
| Opponent late productive cash | 48,449 | 73,826 |
| Our maximum animals | 8.53 | 8.40 |
| Our requested-action PASS share | 25.22% | 25.60% |

Our score changes by only 4,370 coins between the two groups, but opponent
score changes by 31,092. That means the result was driven mostly by opponent
quality rather than the incumbent adapting into a materially stronger mode.

The wins were not all accidental. The 8-melon/8-wheat opening reliably creates
liquidity, the strawberry cohort can produce 80k-105k, and terminal liquidation
left zero sellable product units in every audited game. Those mechanics beat
opponents whose routing, crop choice, or reinvestment produced only 71,388
coins on average.

The losses were also not crashes. Our losing score still averaged 83,059, but
the winners built more productive late economies: 73,826 late productive coins
versus our 54,470. They combined larger investment, more labor throughput,
roughly fourteen animals, and crop diversification instead of relying on one
premium crop. They were able to lead early or overtake around the middle-to-late
transition and then compound the gap.

The incumbent's limiting invariants are visible in both result groups:

- eight hands regardless of workload;
- roughly eight animals despite towns that reward larger animal portfolios;
- about one quarter of requested actions spent passing;
- a large, shared strawberry position exposed to opponent supply and price
  collapse; and
- nearly the same output plan against weak and strong opponents.

## Resilient portfolio v7

The unsubmitted replacement in
[`candidates/resilient_portfolio.py`](../candidates/resilient_portfolio.py)
keeps the incumbent's reliable scheduler while changing the economic policy:

- opens with 1 goose, 2 cows, 2 sheep, 8 melon seeds, 7 wheat seeds, and 9
  hands;
- maintains an eight-animal generic engine, but scales toward 16 only when
  animal-consuming shops justify the cells and labor;
- discounts goals when the opponent already supplies the same products;
- allocates wheat, strawberry, tomato, and carrot capacity from town demand,
  feed needs, and visible rival crops;
- grows to 10 hands after 42 productive cells and 11 when urgent survival
  chores accumulate;
- bounds seed waves, staggers afternoon watering, banks under storage pressure,
  and preserves only animal purchases with remaining-season return; and
- fertilizes only when the incremental crop value exceeds selling the
  fertilizer itself.

## Local promotion evidence

All local matches below use both player seats where the harness supports it.
No execution error occurred.

| Gate | Result | Mean margin | Interpretation |
|---|---:|---:|---|
| Direct v7 vs live incumbent, 32 paired matches | **28-4** | **+7,984** | Strongest causal local comparison |
| Fixed-shop regression suite, 56 matches | **41-15** | **+14,562** | Broad shop/calendar coverage |
| Four independently coded live archetypes, 64 matches | **64-0** | Positive in every family | Robust against reconstructed mid-field styles |
| Frozen actions from all 34 incumbent public games | **28-6** | **+7,875** | Counterfactual on the exact public calendars |
| Frozen actions from current top-10 corpus, 20 traces | **0-20** | **-36,213** | Serious unresolved top-leader risk |

For the direct 28-4 gate, the Wilson 95% interval for win rate is
71.9%-95.0%, and the seed-cluster bootstrap 95% interval for mean margin is
+4,082 to +12,108. The evidence is strong enough to replace the 841.7
incumbent as an experiment, but it does **not** demonstrate a 2,000 rating.

The top-10 trace test is deliberately conservative: the opponents replay fixed
historical actions and cannot react to our changed market behavior. It is not a
true executable clone, yet 0-20 is still negative evidence. The candidate also
lost narrowly in all eight balanced fixed-shop games (mean margin -801) and
went 1-7 against repeated Farmers Market calendars (mean margin -1,311).
Those weaknesses must stay visible when deciding whether to spend a daily
submission slot.

## Release artifact

The verified archive is `dist/resilient-v7-submission.tar.gz` with SHA-256:

```text
1168e841a8a02f6ffeee53f24c2bb0326cb58906dcf14f0c770665f83ab9c14e
```

It contains exactly `main.py`, `candidates/__init__.py`,
`candidates/live_archetypes.py`, and `candidates/resilient_portfolio.py`.
The full suite passed 116 tests and an isolated full-season archive run reached
`DONE` without an agent error. Building and testing this artifact did not
upload it or consume a Kaggle submission.
