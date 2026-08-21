# Kaggriculture submission registry

This is the rollback and score ledger for team `astro`. The machine-readable
source of truth is [`submissions/registry.toml`](../submissions/registry.toml),
and every artifact below is the **exact file downloaded from the corresponding
Kaggle submission**, not a later reconstruction.

Last live check: **2026-08-21 13:51 IST**. Ratings are matchmaking ratings and
can change whenever another public episode completes.

## Current ranking

| Rank | Submission | Strategy | Current rating | Public record | Win rate | Role |
|---:|---:|---|---:|---:|---:|---|
| 1 | `55654212` | Replay-audited throughput v8 | **843.7** | **22-16-0** | 57.9% | Current rating leader |
| 2 | `55631403` | Stable strawberry champion v3 | **832.7** | **24-26-0** | 48.0% | Historical fallback |
| 3 | `55625688` | Replay-derived adaptive hybrid v2 | **767.7** | **17-15-0** | 53.1% | Established baseline |
| 4 | `55623462` | Diversified crop v1 | **662.2** | **13-12-0** | 52.0% | Historical fallback |

V8 peaked at 845.6 and currently leads retained bots at 843.7. V3's 911.3 API
snapshot and user-reported 975 peak occurred after only five early matches; its
mature record is 24-26 and current rating is 832.7. Those peaks were sampling
noise, not stronger mature performance.

## Latest submission episode audit

Thirty-seven downloaded v8 games went 21-16. V8 averaged 96,782 coins, versus
82,642 for v3's mature sample. V8 losses averaged 96,232 against 105,271: herd
and fertilizer gaps were largely fixed, but opponents averaged 33.8 maximum
strawberries versus 20.5 and earned 9,687 more late productive cash. No crash
or liquidation failure occurred.

## Strategy reconstruction record

### 55623462 — diversified crop v1

- Exact artifact: [`55623462-upload.tar.gz`](../submissions/artifacts/55623462-upload.tar.gz)
- Entrypoint: `candidates.crop:agent`
- Opening: 16 melon seeds, 9 wheat seeds, 7 hands, no animals.
- Farm logic: calculate marginal crop value from shared inventory, shop demand,
  pending stock, and visible rival production; later crops can rotate among
  wheat, carrot, tomato, strawberry, and melon.
- Scaling: 7 hands on 25 tiles, 8 on 50, and 10 on larger farms; land is bought
  only after wealth thresholds are met.
- Exit: stop creating terminal chores and liquidate sellable stock on day 29.
- Why it plateaued: no livestock or fertilizer revenue, weak late compounding,
  and high exposure to premium-crop price collapse.

### 55625688 — replay-derived adaptive hybrid v2

- Exact artifact: [`55625688-upload.tar.gz`](../submissions/artifacts/55625688-upload.tar.gz)
- Entrypoint: `candidates.hybrid:agent`
- Opening: 2 cows, 3 sheep, 3 strawberry seeds, 10 wheat seeds, 5 bought wheat,
  and 5 hires; no opening melons.
- Animals: Tetsuya-derived, shop-responsive goals with caps of 3 geese, 12
  cows, 10 sheep, and 15 animals total.
- Crops: residual-value planner based on prices, shops, and visible opponent
  supply; at most 12 new plants per day.
- Scaling: 75 tiles, 12-hand ceiling, no fourth-land branch, day-29 liquidation.
- Why it remains useful: a 32-match sample and exact archive make it the most
  established fallback.
- Why it stopped climbing: the live audit found an invariant conservative
  opening, too few late strawberries, excessive movement and shed trips, and
  weak day-20-to-29 crop compounding.

### 55631403 — stable strawberry champion v3

- Exact artifact: [`55631403-upload.tar.gz`](../submissions/artifacts/55631403-upload.tar.gz)
- Entrypoint: `candidates.champion_strawberry:agent`
- Opening: 1 cow, 2 sheep, 8 melon seeds, 8 wheat seeds, and 8 hands.
- Animals: baseline 4 cows and 3 sheep; shop demand can scale cows to 9 and
  sheep to 8 within a 15-animal cap.
- Crops: 40 strawberries, scaling to 44 with demand, plus shop-triggered tomato
  and carrot sleeves; the opening melon harvest funds recurring production.
- Scaling: 75 tiles, premium fertilization, batched selling, and final-day
  liquidation.
- Reliability change: empty-board geometry stays identical to the proven live
  strawberry policy, but placed animal coordinates and kinds never shift;
  targets never fall below animals already on the board, in the shed, or
  carried by workers.
- Current risk: its 50-game 24-26 record is negative; low labor
  and herd ceilings leave it exposed to diversified late compounding and
  shared strawberry-price competition.

### 55654212 — replay-audited throughput v8

- Exact artifact: [`55654212-upload.tar.gz`](../submissions/artifacts/55654212-upload.tar.gz)
- Entrypoint: `candidates.throughput_portfolio:agent`
- Opening: 2 cows, 2 sheep, 8 melon seeds, 7 wheat seeds, and 9 hands.
- Scaling: relevant shops add two herd slots up to 20; geese require egg demand.
- Crops: v7 feed-safe residual allocation with urgent premium planting.
- Result: 22-16, 843.7 current rating, 845.6 observed peak.
- Current local refinement: rotates at most six uncommitted crop cells toward
  demanded strawberries, fills at most three idle cells with wheat, and hires
  hand 12 only for backlog in diverse towns.

## Exact rollback artifacts

| Submission | Archive SHA-256 |
|---:|---|
| `55623462` | `1d1d6391a0829f9cde6fd451eef9e00ca88ae84ff65352497784bad59a453853` |
| `55625688` | `d10032fa250a1e980f04dd4d711cf7ae724c1138d8f3a1761bda357529d156a2` |
| `55631403` | `ce0711105c1918c3f5d17312dad34105b4acb954bb542660cf38bb6fb7081695` |
| `55654212` | `7b406c20628f00319f8f8cdfc2a4c00b4240240779f6d537409cc5b5e7a76192` |

Run the registry test before using any artifact:

```bash
.venv/bin/pytest -q tests/test_submission_registry.py
```

If a future bot is clearly worse, resubmit the chosen retained archive without
rebuilding it from mutable source files:

```bash
.venv/bin/kaggle competitions submit kaggriculture \
  -f submissions/artifacts/55625688-upload.tar.gz \
  -m "Rollback to exact submission 55625688"
```

Submitting consumes the daily allowance, so first confirm the live score and
run the local archive test. Credentials must remain in the process environment
only; never add a token to this repository.

## Updating this ledger

1. Fetch a read-only snapshot:

   ```bash
   .venv/bin/python -m eval.kaggle_submissions snapshot SUBMISSION_ID --summary-only
   ```

2. Append the observation to `submissions/registry.toml`; update the current
   rating, W-L-T record, current rank, and peak only when the new rating exceeds
   the previous peak.
3. Keep entries in chronological submission order. Ranking is a current view,
   not the storage order.
4. Download every future exact upload immediately with:

   ```bash
   .venv/bin/python -m eval.kaggle_submissions download SUBMISSION_ID \
     --output submissions/artifacts/SUBMISSION_ID-upload.tar.gz
   ```

5. Run the full test suite and commit the registry, artifact, source, and
   evidence together. Do not commit replay blobs, `runs/`, `dist/`, or secrets.
