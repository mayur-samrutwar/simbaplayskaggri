# Live submission audit: 55625688

Audit date: 2026-08-20. Scope: every public Kaggle episode returned for the
`astro` submission, excluding the unrated validation/self episode. The replay
actions were re-executed against the exact episode seeds, and every reported
final reward reconciles to the Kaggle replay.

## Executive verdict

The submitted bot is not failing because it crashes. It is failing because its
typical economic output clusters near $75,000 while stronger opponents
compound premium-crop income in the final third of the season.

- Live record: **14 wins, 13 losses, 0 ties (51.9%)** across 27 public games.
- Ladder rating at the audit refresh: **795.3**. This is a matchmaking rating,
  not the coins earned inside one game.
- Mean final cash: **$76,256** for Astro versus **$76,728** for opponents.
- Astro changes little between wins and losses: $78,578 in wins and $73,756 in
  losses. Opponent quality changes dramatically: $60,391 in Astro wins versus
  $94,321 in Astro losses.
- Against opponents finishing at $90,000 or more, Astro is **1-8**. Against
  opponents at $100,000 or more, it is **0-4**.
- Ten of the 14 wins came against opponents finishing below $70,000.

The strategy therefore beats weak and mid-tier policies but does not scale
against high-output ones. The current animal subsystem is a real strength. The
crop portfolio, late-game reinvestment, labor policy, and routing are the
binding weaknesses.

## What happens in the losses

### The decisive economic split

| Mean per loss | Astro | Winner | Advantage |
|---|---:|---:|---:|
| Final cash | $73,756 | $94,321 | Winner +$20,565 |
| Crop revenue | $37,358 | $80,648 | Winner +$43,291 |
| Animal + fertilizer revenue | $67,503 | $56,134 | **Astro +$11,369** |
| Labor cost | $9,034 | $5,488 | Winner saves $3,546 |
| Strawberry units sold | 74.9 | 188.6 | Winner +113.7 |
| Strawberry revenue | $16,856 | $43,925 | Winner +$27,069 |
| Peak strawberry plants | 9.9 | 34.4 | Winner +24.5 |
| Peak total crops | 38.0 | 65.8 | Winner +27.8 |

This is not an “animals versus crops” guess: Astro already wins the animal plus
fertilizer side by about $11,400 per lost match. It then gives back nearly four
times that advantage in crops. Strawberry is the largest single deficit.

### Astro starts ahead and then stops compounding

Astro was ahead at the end of day 20 in **11 of the 13 losses**. The period
figures below subtract bought-product spend, so opponents' wheat buy/resell
loops cannot masquerade as production.

| Period | Astro productive cash | Winners' productive cash |
|---|---:|---:|
| Days 0-9 | $11,387 | $5,525 |
| Days 10-19 | $43,568 | $36,397 |
| Days 20-29 | $36,914 | $70,116 |

The winners do not simply time one final sale better. They own more recurring
plants and produce approximately 2.5 times as many strawberries. Their average
realized strawberry price is also slightly higher, about $233 versus Astro's
$225, but volume is the dominant difference.

### The opening is invariant and too conservative

In all 13 losses Astro made the same first-turn purchase and reached the same
day-3 footprint:

- five initial hires, two cows, three sheep, three strawberry seeds, ten wheat
  seeds, and five bought wheat;
- ten wheat plants, three strawberry plants, two cows, and three sheep by day 3;
- no opening melons.

Twelve of the 13 winners had melons by day 3; the median winning opening had
roughly 12. That creates a day-10 liquidity wave which is then reinvested in
recurring strawberries and a shop-aligned herd. Astro instead commits most of
its opening capital to a five-animal base and never catches up on recurring
crop capacity.

### Labor is plentiful but inefficient

The bot's requests are usually valid, but valid work is not the same as useful
work. Across the losses it hired 335-341 hands per game and ran 12 hands on 264
of 390 game-days. Winners averaged about 267 hires.

| Mean per loss | Astro | Winner |
|---|---:|---:|
| Movement share | 58.3% | 48.6% |
| PASS share | 17.6% | 16.8% |
| DROP requests | 263.5 | 59.2 |
| PLANT requests | 67.0 | 112.5 |
| WATER requests | 402.5 | 721.4 |
| HARVEST requests | 203.6 | 271.9 |
| Fertilize requests | 39.6 | 62.8 |

The current carrier rule starts returning at hour 17, ten carried units, or
$1,200 of carried value. That creates many small shed trips. The global crop
snake also stops being shed-facing after southern land unlocks. The result is
more movement and four times as many drops while servicing far fewer crops.

Against the nine opponents that scored at least $90,000, the contrast is even
sharper:

| Mean per game | Astro | $90k+ opponent |
|---|---:|---:|
| Final cash | $84,758 | $103,508 |
| Total action slots | 8,472 | 6,602 |
| Productive commands | 2,069 | 2,387 |
| Movement share | 58.1% | 47.4% |
| Productive-work share | 24.4% | 36.3% |
| Hand-days | about 340 | 263 |
| Labor cost | $9,146 | $5,656 |
| DROP requests | 274 | 46 |

Astro pays for roughly 1,870 extra action slots yet completes 318 fewer
productive commands. This is the clearest evidence that adding workers is not
the solution.

There were no unreconciled harvested goods and terminal sellable inventory was
zero in every loss, so liquidation is strong. However, eight animals escaped,
five wheat crops died from drought, and $8,830 of purchased seeds remained
unused across the losses. The scheduler is valid and clean at the finish, but
not reliably deadline-safe or capital-efficient.

## Every loss

`Crop / animal+fertilizer / cost` exactly reconciles as
`$3,000 + crop + animal/fertilizer - cost = final cash`.

| Episode | Opponent | Final cash | Astro crop / A+F / cost | Winner crop / A+F / cost | Why Astro lost |
|---:|---|---:|---:|---:|---|
| 94541741 | GorillaGhost | $60,468-$86,450 | $35,813 / $53,298 / $31,643 | $201,266 / $50,785 / $168,601 | Premium crops decided it: +$22.6k strawberry and +$10.8k melon. Its huge wheat loop was slightly loss-making after its $134.1k wheat spend. |
| 94546207 | Nazariy Karpov | $87,988-$113,942 | $45,403 / $76,080 / $36,495 | $80,848 / $59,603 / $29,509 | +$33.9k strawberry, +$6.7k melon, and $7.0k lower cost overcame Astro's milk advantage. |
| 94547997 | Zhengxu Yu | $79,684-$96,124 | $33,132 / $82,210 / $38,658 | $59,936 / $58,295 / $25,107 | Primarily efficiency: nearly equal gross output, but Astro spent $13.6k more on labor, land, animals, and wheat. |
| 94548914 | Gautier Fauchart | $61,693-$79,968 | $42,068 / $49,194 / $32,569 | $58,621 / $42,969 / $24,622 | +$13.4k melon, +$7.8k strawberry, and cheaper labor/feed. |
| 94549814 | JacobKooi | $95,538-$137,692 | $32,205 / $96,709 / $36,376 | $81,699 / $93,399 / $40,406 | +$45.7k strawberry. The winner earned $116.2k during days 20-29 alone. |
| 94550713 | MakiMakiAi | $59,706-$89,656 | $39,104 / $53,306 / $35,704 | $133,321 / $48,975 / $95,640 | +$38.0k strawberry. Its bulk wheat cycle lost money; strawberry and melon paid for the win. |
| 94552485 | Omer Rehman | $77,583-$92,533 | $24,735 / $85,702 / $35,854 | $58,877 / $60,137 / $29,481 | +$21.1k strawberry, +$16.3k melon, and cheaper labor/feed beat Astro's much stronger animals. |
| 94553380 | Leo Lai | $88,106-$92,218 | $37,649 / $81,088 / $33,631 | $49,666 / $68,368 / $28,816 | Astro earned $703 more gross revenue and lost entirely through $4.8k excess overhead. |
| 94556044 | Hoo Woo | $79,020-$106,207 | $42,775 / $63,970 / $30,725 | $71,966 / $55,675 / $24,434 | +$39.3k strawberry and lower labor/feed cost. |
| 94556944 | KOTHAPALLI DILEEP | $66,952-$91,369 | $32,344 / $63,609 / $32,001 | $58,766 / $58,467 / $28,864 | +$30.6k strawberry despite the opponent making more execution mistakes and discarding output. |
| 94558740 | Julian Kerignard | $53,813-$65,810 | $46,589 / $34,108 / $29,884 | $67,683 / $16,092 / $20,965 | A low-capex, 50-tile strawberry specialist: +$41.5k strawberry with $8.9k lower cost. |
| 94561431 | Andrey Aristov | $67,113-$72,548 | $40,822 / $57,663 / $34,372 | $58,421 / $43,287 / $32,160 | +$16.8k strawberry and lower overhead; it won despite 14 animal escapes and substantial waste. |
| 94562325 | BONPU | $81,166-$101,657 | $33,012 / $80,608 / $35,454 | $67,360 / $73,694 / $42,397 | +$36.4k strawberry and +$10.5k milk; late scale repaid the higher investment. |

The common winning shape is an early melon bootstrap, a much larger recurring
strawberry block, fertilizer on premium recurring crops, a shop-responsive
herd, and more revenue-producing work per hired hand. The exceptions reinforce
the same diagnosis: Leo won on overhead alone, and Julian won with only 50
tiles because compact specialization was more efficient than Astro's fixed
75-tile plan.

## What the wins really prove

Gross sales are misleading because some opponents buy and resell thousands of
wheat units. For each win, the audit uses productive cash: total sales minus
`BUY_PRODUCT` wheat spend. Astro had higher productive cash in 12 of 14 wins.

“Genuine” below means the productive policy created value; it does not mean the
opponent was leaderboard-caliber. Ten wins were still against sub-$70k bots, so
several genuine edges merely punished an obviously bad product mix.

Classification:

- **8 convincing strategy wins:** the chosen product mix generated a real
  productive-cash advantage;
- **4 mixed wins:** Astro had a real shop-fit or liquidation advantage, but the
  opponent's droughts, escapes, unsold goods, or bad allocation materially
  amplified it;
- **2 fragile wins:** Astro produced slightly less and won only by spending less.

| Episode | Opponent | Final cash | Verdict | What actually produced the win |
|---:|---|---:|---|---|
| 94540866 | Hubbahub | $104,441-$62,373 | Mixed | Real milk/strawberry shop fit, amplified by 22 opponent drought losses, five bought-but-unplaced cows, and $11.2k unsold goods. |
| 94542680 | Nika Chaduneli | $53,507-$43,462 | Mixed | Useful geese/diversification and lower cost; opponent kept six sheep with no Yarn shop and reached 33 weeds. |
| 94543531 | Firman Imam | $96,824-$81,212 | **Genuine** | With the same sheep count Astro earned $40.8k wool versus $27.0k, plus more milk and a better diversified crop mix. No material opponent collapse. |
| 94544412 | anthony sinchi | $106,784-$99,832 | Mixed | Three Yarn shops made Astro's $52.8k wool correct, but the opponent left about $8.6k unsold and had drought/escape losses; clean liquidation was decisive. |
| 94545303 | onepunch999 | $51,489-$51,153 | **Fragile** | A $336 cost-only escape. The opponent overbuilt ten sheep with no Yarn and accumulated weeds; Astro itself lost three cows. |
| 94547099 | ghostiee11 | $73,972-$55,918 | **Genuine** | Four Yarn shops and egg demand made $58.3k wool plus eggs superior to the opponent's 38-strawberry, zero-strawberry-demand portfolio. |
| 94551604 | Ani | $78,849-$67,434 | Mixed | Correct Yarn response produced $52.2k wool versus $16.1k; opponent lost 54 crops and five sheep. Astro also lost four animals, exposing its feed bug. |
| 94554271 | Arunabh Gupta | $71,228-$47,175 | **Genuine** | $33.4k strawberry plus $17.9k wool matched shops; opponent planted no strawberry and its wheat churn was unprofitable. |
| 94555158 | Kushpreet Singh | $100,903-$84,382 | **Genuine** | $61.7k milk versus $42.9k plus eggs; opponent ignored three egg-demanding shops. |
| 94557850 | dddmd | $93,712-$51,642 | **Genuine** | Six milk-demanding shops justified 11 cows and $65.8k milk. Opponent put 13 animals into wool/egg despite no such demand. |
| 94559644 | xiaocai liu | $97,822-$83,038 | **Genuine** | Eight sheep matched two Yarn shops, producing $39.7k wool versus $2.9k; opponent also overcropped and left goods/seeds unused. |
| 94560538 | Boltuzamaki | $44,298-$18,217 | **Genuine** | Geese and carrots matched four egg and three carrot outlets; opponent produced no eggs and too few carrots. |
| 94584693 | Pranav Gupta | $66,106-$42,145 | **Genuine** | Wool and eggs matched the town. After removing $477k of wheat churn, Astro's productive cash led by $36.6k. |
| 94585625 | DC | $60,154-$57,496 | **Fragile** | Astro's productive cash was $370 lower; it survived by spending about $3.0k less against a mismatched no-goose/no-carrot opponent. |

The wins are therefore not all fake. The reliable strengths are:

- shop-responsive selection among cows, sheep, and a small number of geese;
- rejecting livestock that has no corresponding town demand;
- self-grown feed and avoiding loss-making wheat churn;
- stronger crop survival and weed control than most weak opponents;
- complete terminal liquidation; Astro ended all 27 public matches with zero
  sellable product in the shed or workers' inventories.

They do **not** prove that twelve hands, a five-animal opening, three opening
strawberries, or 75 tiles are optimal. More bodies did not cause the wins.
Astro generally hired more hands than its opponents; strong opponents produced
more with fewer. Product mix, timing, and work density mattered more than unit
count.

Two further blind spots appear across the full sample:

- Astro planted **one tomato in all 27 matches**, despite repeated Pizza Shop
  and Farmers Market demand. Zhengxu used 14 tomatoes and five geese to beat a
  branch the submitted policy barely recognizes.
- Astro buys about 306 wheat units per game for $12.9k, plants about 39.5 wheat
  crops, and still sells about 140 wheat for $6.3k. Farm wheat and future feed
  demand are not managed as one inventory. Routing then forces emergency feed
  purchases; 15 animals escaped across five matches.

High-output opponents also timed the crop calendar better. They planted their
main melon wave on days 0-1 and sold around days 10-13; Astro planted most
melons on days 5-8 and sold into the later glut. Against $90k+ opponents Astro
realized about $159 per melon versus $176. Their main strawberry cohorts were
staggered through days 9-13 and produced heavily during days 20-29.

## Why the 89.8% local result did not transfer

The local candidate's mean cash, $74,986, was close to its live $76,256. The
failure was the opponent model: local emulators averaged only about $58,757,
whereas live opponents averaged $76,728 and loss-causing opponents averaged
$94,321.

The “leaderboard” emulators all import the same `hybrid_core.py` used by the
candidate. They vary openings, caps, and crop/animal modes, but share routing,
labor selection, crop servicing, carrier returns, market timing, and several
valuation assumptions. Same-core opponents accounted for **128 of 176 local
games (72.7%)**. The suite therefore tested policy parameters against relatives
of the same scheduler, not robustness against independent top-bot
implementations.

This created three blind spots:

1. It could not expose the shared high-movement, high-hire, micro-drop behavior.
2. It reproduced weak late compounding, so a $75k candidate looked dominant
   against $59k opponents.
3. It promoted a residual crop scorer even though the real replay evidence
   showed leaders maintaining roughly 35-42 strawberries. The scorer values
   strawberry's base four-unit lifetime and does not include the full effect
   of repeated fertilizer doubling, so it systematically underallocates the
   crop that decided most live losses.

The local win rate measured emulator similarity, not leaderboard readiness.

## Required strategy changes

These changes preserve the proven animal and liquidation subsystems while
addressing the live failure mode.

1. **Restore a premium-crop engine.** Test an 8-12 melon bootstrap with 4-8
   feed-wheat tiles, then stagger cohorts toward roughly 30-38 active
   strawberries by days 9-13 when remaining shop demand supports them. Reduce
   the current late melon bias and make crop value explicitly
   fertilizer-aware.
2. **Keep shop-responsive animals, but make them marginal.** Start with a
   smaller balanced base, branch toward milk/wool/eggs after shop evidence, and
   subtract visible opponent capacity. Do not remove the subsystem that beats
   winners by $11k per loss.
3. **Replace global routing with quadrant-local service routes.** Put recurring
   crops and animals in shed-facing strips, assign persistent service regions,
   and use one or two batch couriers instead of every worker returning small
   loads.
4. **Cap routine labor near 9-10 hands.** Use 11-12 only for measured deadline
   backlog. The 11th and 12th daily hires cost $89 and $144; avoiding routine
   spikes can save roughly $4-5k and would have flipped the Leo loss.
5. **Make feed and water deadlines hard constraints.** Reserve two days of feed
   before herd expansion, consume farm wheat before purchasing more, do not
   sell wheat that must later be repurchased, and pre-assign any tile/animal
   with one missed day.
6. **Gate land by projected occupancy and travel cost.** Do not automatically
   buy 75 tiles. A compact 50-tile branch is valid when demand supports a narrow
   portfolio.
7. **Optimize days 20-29 explicitly.** Track expected remaining harvests and
   net late cash, stop seeds that cannot pay back, preserve collection/sale
   slots, and sell after town-consumption ticks when storage permits.
8. **Preserve zero-inventory liquidation.** This is one of the few live-proven
   execution advantages and should remain a hard regression gate.

## Promotion gates for the next bot

Do not promote another strategy from win rate alone. The next suite needs
independent schedulers for these replay-observed archetypes: late strawberry
specialist, melon-bootstrap hybrid, milk specialist, wool/strawberry hybrid,
mixed animal/strawberry scaler, wheat-churn bot, and mechanically noisy
low-cost bot.

Before another Kaggle submission, require all of the following on disjoint
paired-seat seeds:

- opponent emulators independently reproduce live-like scores and trajectories;
- at least $60k average productive cash during days 20-29 against the strong
  archetype set, up from the current $36.9k in losses;
- demand-supported strawberry cohorts reach at least 28-35 active plants and
  materially exceed the current 75 units sold;
- routine hires stay near 10, mean labor cost approaches the strong-opponent
  range, productive-work share reaches roughly 35%, movement share falls below
  roughly 50%, and drop requests fall below roughly 75 per game;
- no runtime errors, no midgame escapes, near-zero unused seed cost, and zero
  terminal sellable inventory;
- report both win rate and score distribution, with separate results against
  opponents that score at least $90k. A bot that only beats $50k-$60k emulators
  is not a promotion candidate.
- the strong-archetype economic target is approximately $130k gross sales at
  no more than $32k cost, rather than winning by suppressing a weak emulator.

## Reproducible artifacts

- `replays/submission-55625688/analysis.json`: exact replay reconstruction.
- `replays/submission-55625688/live_report.json`: per-match and grouped metrics.
- `replays/submission-55625688/live_matches.csv`: flat comparison table.
- `eval/report_live_submission.py`: report generator, including normalized
  productive-cash and early/middle/late-period metrics.
