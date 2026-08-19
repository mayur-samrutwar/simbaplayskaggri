# Kaggriculture strategy notebook

Status: replay-derived hybrid promoted on 2026-08-19 against
`kaggle-environments==1.32.7`. Every claim below is a hypothesis until it wins
paired-seat holdout games.

## Objective

The ladder rewards only win/loss/tie. Optimize paired win rate and worst-case
robustness before average cash. A one-coin win is strategically complete.

## Promoted hybrid opening

The current incumbent begins with two cows, three sheep, ten wheat seeds, three
strawberry seeds, five feed wheat, and five initial hands. This is the most
efficient observed five-animal opening, but its fixed crop book was replaced:
subsequent seeds are selected from marginal post-glut value using live town
demand and visible opponent crops. The flock branches toward milk, wool, or up
to three geese as shops unlock, with a hard cap of fifteen animals.

The design is a synthesis of the replay audit: tetsuya's compact opening and
egg awareness, Arman's balanced crop/animal economics, Ryo's operational
precision, ReCurSiON's self-grown feed, and peikopon's small demand-triggered
tomato/carrot positions. It deliberately rejects the leaderboard family's
100-tile sheep escalation, fixed 35–42 strawberry book, zero-egg blind spot,
and repeated wheat buy/sell churn.

The earlier 16-melon/9-wheat crop strategy remains in `candidates/crop.py` as a
regression opponent.

## Competing hypothesis: goose/fertilizer rush

The opening to beat is eight hires, nine geese, and nine wheat in the first
market queue:

- hires cost `1+1+2+3+5+8+13+21 = 54`
- geese cost `9*300 = 2700`
- the first nine wheat cost about `244` on the dynamic curve
- total is about `2998`, and the ten orders exactly fill the turn cap

Nine workers can build, pick up, place, and service the flock. Fertilizer starts
near $100 and every surviving animal exposes one unit per day, making it the
fastest generic payback. Eggs tolerate a glut much better than milk, wool,
melon, or strawberry.

This opening has a liquidity trap: spending almost all $3000 can leave no money
for next-day wheat. Test both eight-hire and seven-hire variants, deliberate
first-day feed skipping, and same-day fertilizer return/drop/sale routes.

## Labor curve

The cumulative cost for `h` same-day hands is `Fib(h+2)-1`:

| Hands | Daily cost |
|---:|---:|
| 8 | 54 |
| 10 | 143 |
| 12 | 376 |
| 14 | 986 |
| 15 | 1596 |

Early labor is almost free; late marginal hands are not. Hire only when their
remaining actions can cover routing plus high-value work. Water/feed survival,
clipping prevention, harvest, and liquidation outrank expansion.

## Crop economics at base price

| Crop | Normal harvest | Seed | Gross | Net before labor |
|---|---:|---:|---:|---:|
| Wheat | 4 at age 4 | 10 | 100 | 90 |
| Carrot | 3 at age 3 | 20 | 105 | 85 |
| Tomato | 4 across ages 8–11 | 50 | 240 | 190 |
| Strawberry | 4 across ages 10–16 | 100 | 480 | 380 |
| Melon | 6 at age 10 | 80 | 1500 | 1420 |

Melon has spectacular first-batch economics but a quadratic glut curve; its
price reaches the $1 floor after roughly 158 net units of oversupply. It is an
opening/portfolio asset, not a blind monoculture. Latest practical planting
days for a day-29 harvest are approximately wheat 25, carrot 26, melon 19,
tomato 18, and strawberry 13, before routing/liquidation buffers.

Fertilizer opportunity thresholds:

- wheat: use only below the value of two extra wheat
- carrot: below one extra carrot
- tomato: a well-timed first application can add three tomatoes
- strawberry: one application can cover two scheduled yields
- melon: normally adds no final yield when daily watering already reaches cap

## Demand adaptation

Shops unlock every three days with replacement. Duplicate shops matter more
than variety. Estimate daily product drain as:

```text
wheat      = 1 + 6*(bakery+pizza+brunch+ice_cream+farmers_market)
egg        = 1 + 6*(bakery+brunch)
milk       = 1 + 6*(pizza+ice_cream+smoothie)
tomato     = 1 + 6*(pizza+farmers_market)
strawberry = 1 + 6*(brunch+ice_cream+smoothie+farmers_market)
carrot     = 1 + 12*pet_cafe + 6*farmers_market
wool       = 1 + 12*yarn_store
melon      = 1
```

Delay speculative cows/sheep until shops justify them. Carrot, tomato, and egg
have scarcity hinges and become attractive after demand crosses their anchor
throughput. Subtract visible opponent production before choosing a portfolio.

## Market timing

- Town consumption happens after player orders at hours 0/4/8/12/16/20. The
  newly scarce price is visible on hours 1/5/9/13/17/21.
- A unit can return and `DROP`, then a `SELL` order can consume that deposit in
  the same turn.
- Premium output should be sold before a visible opponent dump, or aligned to
  the opponent's same queue index to share lockstep quotes.
- At the $1 floor, sales destroy the item without increasing market inventory.
  Hold nonterminal premium stock for town recovery when storage permits.
- Wheat is both feed and a counter-position against an opponent animal rush.

## Terminal rules

The last agent call is step 718 (day 29, hour 22). Day 29's normal end-of-day
inventory drop never runs. Target:

- harvest and start returning by hour 20
- drop and sell on hour 21
- keep hour 22 as the backup liquidation turn

Unsold shed or carried inventory, immature assets, seeds, structures, and land
have zero terminal value.

## Promotion protocol

For every candidate:

1. Run engine contract tests and black-box `main.py` smoke games.
2. Play identical fixed seeds in both seats.
3. Compare against starter, goose rush, crop rush, demand-following, wheat
   counter, premium dumper, and the current incumbent.
4. Track crashes, silent no-ops, escapes/weeds, held-yield clipping, shed
   overflow, idle/movement share, unsold inventory, and realized sale prices.
5. Promote on holdout win-rate improvement with zero reliability regressions,
   not on a few high-money games.
