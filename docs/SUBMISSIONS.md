# Kaggriculture submission registry

This is the rollback and score ledger for team `astro`. The machine-readable
source of truth is [`submissions/registry.toml`](../submissions/registry.toml),
and every artifact below is the **exact file downloaded from the corresponding
Kaggle submission**, not a later reconstruction.

Last live check: **2026-08-20 02:26 IST**. Ratings are matchmaking ratings and
can change whenever another public episode completes.

## Current ranking

| Rank | Submission | Strategy | Current rating | Public record | Win rate | Role |
|---:|---:|---|---:|---:|---:|---|
| 1 | `55631403` | Stable strawberry champion v3 | **911.3** | **4-1-0** | 80.0% | Provisional rating leader |
| 2 | `55625688` | Replay-derived adaptive hybrid v2 | **793.0** | **15-14-0** | 51.7% | Established baseline |
| 3 | `55623462` | Diversified crop v1 | **662.2** | **13-12-0** | 52.0% | Historical fallback |

The latest bot began at 600, rose through 711.9 and 819.2, dipped to 816.3
after its first loss, and then climbed to 911.3. It leads the internal rating
table, but five matches are not enough to retire submission `55625688`; the
793 bot remains the mature comparison baseline because it has 29 public games.

## Latest submission episode audit

Validation episode `94647666` completed successfully but is excluded from the
rated record. All five public episodes returned by Kaggle were counted:

| Episode | Opponent | Result | Astro | Opponent |
|---:|---|---:|---:|---:|
| `94649372` | Vandana Pathania | Win | 105,654 | 55,545 |
| `94651042` | Vasilii Buzmakov | Win | 79,962 | 57,312 |
| `94652715` | ayushk_empire | Win | 81,861 | 47,762 |
| `94654391` | Denis | Loss | 88,226 | 109,204 |
| `94656075` | F.A.Nina | Win | 75,250 | 74,181 |

The loss was not a crash or liquidation failure: the bot still produced
88,226 coins, but Denis produced 109,204. That is evidence that the strawberry
specialist still needs protection against stronger diversified high-output
farms.

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
- Why it remains useful: a 29-match sample and 793 rating make it the most
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
- Current risk: only five live games, one loss to a 109k diversified opponent,
  and continued exposure to shared strawberry-price competition.

## Exact rollback artifacts

| Submission | Archive SHA-256 |
|---:|---|
| `55623462` | `1d1d6391a0829f9cde6fd451eef9e00ca88ae84ff65352497784bad59a453853` |
| `55625688` | `d10032fa250a1e980f04dd4d711cf7ae724c1138d8f3a1761bda357529d156a2` |
| `55631403` | `ce0711105c1918c3f5d17312dad34105b4acb954bb542660cf38bb6fb7081695` |

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
