# Leaderboard Replay Analysis

## Scope and evidence boundary

This audit covers the ten supplied leaderboard submission IDs and the latest ten episode references returned for each submission. That is **100 submission-episode references covering 80 unique Kaggriculture episodes**; the difference exists because a match between two audited submissions appears in both submissions' latest-ten lists.

The observed results below come from downloaded Kaggle replay JSON, summarized in [`summary.csv`](../replays/leaderboard/summary.csv) and [`analysis.json`](../replays/leaderboard/analysis.json). Records are ten-match snapshots against mostly strong opponents, not each bot's complete leaderboard record, and the rows are not statistically independent. Strategy descriptions are behavioral inferences from repeated actions and state transitions; the original competitors' source code is not available.

The local results later in this document are a separate evidence class. They use replay-derived **emulators** implemented in this repository. Those tests establish that our policy beats the emulators over the tested seeds; they do not prove the same win rate against the original private leaderboard programs.

**Post-submission correction (2026-08-20):** live submission 55625688 went
14-13, and the 89.8% emulator result materially overstated strength because
same-core opponent policies shared the candidate's scheduler. The replay facts
in this document remain useful; its local promotion conclusion is superseded by
the [27-match live audit](LIVE_SUBMISSION_AUDIT.md).

## Observed ten-match snapshot

Revenue columns are mean dollars per game. Animal revenue is egg, milk, and wool; fertilizer is listed separately. “Land” is the mean number of extra quadrants purchased beyond the starting 25 tiles.

| Submission | Team | W–L | Mean score | Mean margin | Crop rev. | Animal rev. | Fert. rev. | PASS | Hires | Land |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 55574890 | tetsuya | 6–4 | 100,071 | +4,413 | 61,079 | 54,646 | 13,091 | 18.9% | 311.4 | 2.0 |
| 55614463 | Ryo Hasegawa | 7–3 | 86,979 | +3,978 | 61,477 | 40,626 | 11,154 | 4.3% | 289.1 | 2.0 |
| 55540317 | カワシギ | 2–8 | 81,027 | −6,117 | 70,011 | 45,715 | 13,401 | 8.1% | 277.0 | 2.4 |
| 55617399 | Arman Tuganbaev | 9–1 | 108,207 | +8,911 | 67,646 | 55,493 | 12,291 | 5.7% | 279.8 | 2.1 |
| 55491717 | ReCurSiON | 2–8 | 86,282 | −7,781 | 54,535 | 47,319 | 11,659 | 14.0% | 262.2 | 2.0 |
| 55609129 | Kobe BRYANT | 2–8 | 90,301 | −7,395 | 73,577 | 42,932 | 13,002 | 8.2% | 277.0 | 2.0 |
| 55577827 | peikopon | 4–6 | 81,599 | −4,307 | 70,414 | 38,783 | 12,817 | 9.3% | 277.6 | 2.1 |
| 55610626 | Xiaowenhao404 | 1–9 | 80,848 | −7,952 | 84,415 | 43,905 | 12,977 | 7.5% | 277.0 | 2.3 |
| 55489809 | Efe Can Celiksoy | 4–6 | 94,343 | −3,307 | 73,487 | 50,317 | 12,872 | 9.6% | 277.0 | 2.0 |
| 55576886 | Galaxantic | 2–8 | 82,974 | −7,048 | 75,715 | 42,837 | 12,851 | 8.2% | 277.0 | 2.4 |

Arman had the strongest observed combination: nine wins, the highest mean score, the largest positive margin, and substantial revenue on both sides of the farm. Tetsuya was the other bot above $100,000 mean cash. Ryo's score was lower, but its 7–3 record and extremely low PASS rate show that raw cash is not the only signal of ladder strength.

## Shared leaderboard strategy

The field is dominated by a related hybrid template:

- Six bots—カワシギ, Kobe, peikopon, Xiaowenhao404, Efe, and Galaxantic—share a day-0 footprint of roughly **2 cows, 2 sheep, 12 melons, 7 wheat seeds, and 8 bought wheat**. Ryo is a close relative at 2 cows, 2 sheep, 11 melons, and 6 wheat seeds.
- These bots expand toward approximately 14–16 cattle/sheep, 35–42 strawberry plants, recurring wheat cohorts, and normally 75 tiles. Some buy the fourth quadrant when a sheep-heavy branch becomes large.
- Arman uses a distinct **4-sheep, 7-melon, 5-wheat** opening, then adds cows and diversified crops.
- ReCurSiON opens **1 cow, 4 sheep, 4 melons, and 5 wheat**, then follows a mostly fixed strawberry/wheat plan.
- Tetsuya opens **2 cows, 3 sheep, 10 wheat, and 3 strawberries**, skipping opening melons and later adding a small number of geese when egg shops justify them.
- Every bot combines livestock products, daily fertilizer, a feed-wheat base, and premium crops. This recurring animal income is the central reason the old crop-only agent lost badly even when its crop revenue exceeded its opponent's crop revenue.
- Nine of the ten bots bought no geese and sold no eggs. Tetsuya was the only egg-aware entry, averaging just 0.9 goose and 27.7 eggs per game. Bakery and Brunch egg demand is consequently one of the clearest residual niches.
- Tomato is also neglected: only tetsuya, Ryo, Arman, and peikopon sold meaningful quantities. Small tomato positions occasionally realized very high scarcity prices.
- Premium output is fragile. Large fixed milk, wool, melon, or strawberry cohorts can collapse toward the $1 floor when both players choose the same product. The strongest policies diversify and react before committing more capacity.
- Terminal execution is generally excellent. Nine teams ended with zero shed/carried units on average; ReCurSiON averaged only 2.5. A viable challenger must match that liquidation discipline.

## Team-specific findings and counters

### tetsuya — 55574890

Observed strategy: balanced 2C/3S hybrid, no opening melon wave, a strong wheat/strawberry base, and limited goose purchases after egg shops appear. It averaged 8.5 cows, 5.6 sheep, 0.9 goose, 35 strawberry seed purchases, and $33,627 milk plus $32,695 strawberry revenue.

Strengths: diversification, the only meaningful egg response in the sample, $100,071 mean cash, and zero terminal inventory. Its 6–4 record remained positive despite facing other leaders.

Weaknesses: 18.9% PASS was the highest observed, and 311.4 hires created substantial routing overhead. The no-melon opening leaves early melon scarcity less contested, while its goose response remains small.

Counter: take only residual animal capacity, use an early melon position when the visible market supports it, and scale eggs beyond tetsuya only when Bakery/Brunch demand and current egg inventory justify the service cost. A lower-PASS, 12-hand-capped version of its balanced opening is preferable to simply copying its labor schedule.

### Ryo Hasegawa — 55614463

Observed strategy: the most crop-diverse member of the 2C/2S family. It averaged 54 carrots and 51 tomatoes sold, in addition to strawberry, melon, wheat, milk, and wool. Its 4.3% PASS rate was the best in the sample.

Strengths: 7–3 record, broad product coverage, balanced 7.6-cow/6.4-sheep herd, aggressive utilization, and no terminal waste.

Weaknesses: no egg production, only $16,231 mean milk revenue despite 7.6 cows, and $7,457 mean labor cost. Its broad portfolio is operationally strong but often competes in already crowded milk and strawberry markets.

Counter: do not fight its diversified farm everywhere. Subtract its visible supply from demand, emphasize eggs and whichever animal side it underweights, and use market timing rather than a larger fixed farm.

### カワシギ — 55540317

Observed strategy: common 2C/2S opening, large wheat/strawberry book, roughly 15.6 animals, and frequent fourth-quadrant expansion. It earned $28,006 from wool and sold 731 wheat per game, but produced no tomato or eggs.

Strengths: high fertilizer output, substantial wool, and $70,011 crop revenue.

Weaknesses: 2–8 record, −$6,117 mean margin, 2.4 land purchases, and a crowded fixed portfolio. Its extra capacity did not translate into a winning margin.

Counter: avoid matching its wool and strawberry supply, target egg/tomato scarcity, and let its fourth-land and feed costs dilute the value of its extra output.

### Arman Tuganbaev — 55617399

Observed strategy: four-sheep opening followed by a powerful balanced farm averaging 8.9 cows, 6.2 sheep, 38 strawberries, plus carrots and tomatoes. It generated $40,636 from strawberry, $33,101 from milk, and $22,392 from wool per game.

Strengths: 9–1, $108,207 mean cash, +$8,911 margin, low PASS, strong crop and animal revenue, and good diversification. This was the strongest replay target.

Weaknesses: no eggs and an unusually high $9,119 labor bill despite only 279.8 hires, implying expensive high-headcount days. The four-sheep opening also declares its early wool exposure immediately.

Counter: use visible residual demand rather than mirroring its herd, exploit Bakery/Brunch eggs, smooth labor to avoid its Fibonacci spikes, and sell competing premium batches before its predictable large liquidation.

### ReCurSiON — 55491717

Observed strategy: fixed 1C/4S opening, then 9C/4S unless the first unlocked shop is Yarn, in which case it moves toward 6C/7S. It plants about 36 strawberries and 143 wheat per game and largely ignores later shop changes.

Strengths: excellent fertilizer-supported strawberries—about 281 sales from 35.7 active plants—and more self-grown feed than the common template. In direct episode 94473239, it beat Kobe 86,784–80,994 despite lower gross revenue because it spent $11,607 less.

Weaknesses: 14.0% PASS, costly 13/14-hand spikes, fixed crop choices, no egg/carrot/tomato production, several systematic missed wheat harvests, and a late cow that may not be placed until day 21. Episode 94498749 lost three cows together on day 14.

Counter: identify its visible 1C/4S signature, avoid wool unless Yarn demand is unusually high, attack eggs/tomatoes/carrots, cap labor at 12, and front-run its day-opening premium sales.

### Kobe BRYANT — 55609129

Observed strategy: extremely repeatable 2C/2S + 12-melon opening, animal additions in two-unit blocks through day 11, 38 strawberries, 125 wheat plantings, and five carrots. It selects between cows and sheep using early milk-versus-Yarn evidence but barely changes its crop book.

Strengths: zero escapes in ten games, roughly 321 FEED and 318 CARE actions per game, 8.2% PASS, a smooth 12-hand ceiling, zero terminal products, and the sample's highest single score of 142,806.

Weaknesses: extreme market dependence. Episode 94519039 fell to 38,483 when 237 milk earned only $8,416, 164 wool earned $3,918, and 274 strawberries earned $11,135. It also finishes every match with eight unused carrot seeds and eight unused wheat seeds.

Counter: recognize the 12-melon cohort and sell before its day-10 dump, wait until its day-11 animal mix is locked, then supply later shop niches it cannot cover. Do not duplicate a product already approaching a glut.

### peikopon — 55577827

Observed strategy: Kobe-like backbone with better crop branching. It varies between 5–35 carrots and 0–4 tomatoes, while most games finish near 10C/4S. An early Yarn Store can trigger a 6C/12S, 100-tile branch.

Strengths: useful late carrot rotations and the clearest proof of tomato scarcity capture. In episode 94526998, 11 tomatoes earned $5,130—$466 each.

Weaknesses: its animal decision locks too early. Episode 94510139 eventually had four Yarn Stores but remained at four sheep; the opposite early-Yarn branch overexpanded in episode 94451134, spending $64,639 and losing six sheep at the terminal transition.

Counter: copy its small demand-triggered tomato/carrot positions, but not its fourth-land branch. When it expands into early wool, choose other products; when Yarn arrives late, add the sheep capacity it can no longer deploy efficiently.

### Xiaowenhao404 — 55610626

Observed strategy: common 2C/2S opening with the largest wheat turnover—947 units and $42,674 wheat revenue per game—plus 42 strawberries and about 15 animals. It produced no tomatoes or eggs and bought 2.3 extra quadrants on average.

Strengths: the highest observed crop revenue at $84,415 and broad wheat throughput.

Weaknesses: 1–9 record, −$7,952 margin, fourth-land use in some games, and heavy wheat turnover that does not convert gross crop revenue into final cash.

Counter: do not chase its gross wheat volume. Keep a stable private feed reserve, buy after its wheat dumps depress price, and earn from egg/tomato or residual animal markets instead.

### Efe Can Celiksoy — 55489809

Observed strategy: cow-heavy common template that settles almost exactly at 10C/4S, with 17 melons and 37 strawberries. It sold 278 milk for $36,635 per game and had the third-highest mean score overall, behind Arman and tetsuya, at $94,343.

Strengths: strong milk engine, substantial crops, simple and consistent capacity, and no terminal waste.

Weaknesses: predictable cow concentration, only $13,682 wool, no tomatoes or eggs, and a negative ten-match margin.

Counter: avoid shared milk gluts; use wool when Yarn demand exceeds its four-sheep output, and prefer eggs/tomatoes for shops it does not cover.

### Galaxantic — 55576886

Observed strategy: sheep-heavy common family, averaging 8.2 cows, 7.4 sheep, 40 strawberries, and 687 wheat sales. It frequently bought the fourth quadrant and produced no tomato or eggs.

Strengths: $75,715 crop revenue and $24,342 wool revenue.

Weaknesses: 2–8, −$7,048 margin, 2.4 extra land purchases, and another crowded strawberry/wool portfolio whose capacity did not repay its expansion.

Counter: let its extra land and sheep depress wool, then select residual milk only if price supports it; otherwise exploit egg, tomato, and carrot demand with a smaller 75-tile farm.

## Replay-derived final strategy

The promoted local policy is [`candidates/hybrid.py`](../candidates/hybrid.py), exposed to Kaggle through [`main.py`](../main.py). It keeps the strongest observed five-animal shape while replacing the leaders' fixed crop allocation with live marginal decisions.

Its current policy is:

- opening: **2 cows, 3 sheep, 3 strawberry seeds, 10 wheat seeds, 5 market wheat, and 5 hands**;
- animal targets: tetsuya-style shop response, including up to three geese for Bakery/Brunch, with caps of 12 cows, 10 sheep, 3 geese, and 15 total animals;
- crops: maintain farm-grown feed, then score crops from live town demand, shared prices, and visible opponent production;
- infrastructure: normally 75 tiles, no fourth quadrant;
- workload: at most 12 new plantings per day and 12 hands, with dynamic hires rather than replayed fixed schedules;
- fertilizer: apply to tomato/strawberry only when projected incremental crop value is at least 1.2 times its sale value;
- market: retain a multi-day feed reserve, rank same-turn sales by value, and hold deeply depressed premium goods when storage and horizon permit;
- terminal: stop feed/care that cannot create another production refresh, collect existing output, return early, and liquidate carried plus shed inventory.

This design deliberately combines what replay evidence supported—hybrid income, cared animals, fertilizer-enhanced recurring crops, self-grown feed, 75-tile discipline, and clean liquidation—while rejecting fixed premium cohorts, uncontrolled fourth-land expansion, 13/14-hand spikes, and zero-egg blind spots.

## Local emulator tests

### What these tests mean

The local opponents are behavioral approximations derived from the replays, not downloaded copies of the private bots:

- [`leaderboard_common.py`](../candidates/leaderboard_common.py) represents the common 2C/2S, 12-melon family.
- [`leaderboard_arman.py`](../candidates/leaderboard_arman.py) represents Arman's sheep-heavy balanced branch.
- [`leaderboard_tetsuya.py`](../candidates/leaderboard_tetsuya.py) represents tetsuya's egg-aware balanced branch.
- Other stress opponents cover crop-only, livestock-only, anti-melon, adaptive-opening, and an earlier hybrid counter.

The holdout and stress manifests record [`variant_tetsuya_dynamic_crops.py`](../candidates/variant_tetsuya_dynamic_crops.py) as the candidate. Its policy values are identical to the currently promoted `candidates/hybrid.py`; the separate filename was retained so experiments could be run without overwriting the incumbent during selection.

The initial four-way emulator league used seeds 0–7, both seats, and 96 matches. Its replay-style tetsuya emulator led at 35–13; the then-current counter was 24–24. That result motivated adopting tetsuya's opening/animal branch and replacing its fixed crops with residual-demand selection. See [`leaderboard-league-s0-7.json`](../runs/leaderboard-league-s0-7.json).

### Disjoint-seed holdout, seeds 4–11

| Emulator | Matches | W–L | Win rate | Mean score | Mean margin | Errors |
|---|---:|---:|---:|---:|---:|---:|
| Arman | 16 | 15–1 | 93.8% | 60,574 | +19,459 | 0 |
| Common family | 16 | 13–3 | 81.3% | 67,493 | +12,662 | 0 |
| Earlier hybrid counter | 16 | 14–2 | 87.5% | 76,279 | +1,717 | 0 |
| Tetsuya | 16 | 13–3 | 81.3% | 78,061 | +5,155 | 0 |
| **Total** | **64** | **55–9** | **85.9%** | **70,602** | **+9,748** | **0** |

The earlier hybrid was the closest holdout opponent: the final policy won 14–2 but by only +$1,717 mean, so this matchup remains a useful regression gate.

Exact holdout manifests: [Arman](../runs/dynamic-vs-arman-holdout-s4-11/summary.json), [common family](../runs/dynamic-vs-common-holdout-s4-11/summary.json), [earlier counter](../runs/dynamic-vs-counter-holdout-s4-11/summary.json), and [tetsuya](../runs/dynamic-vs-tetsuya-holdout-s4-11/summary.json).

### Stress set, seeds 12–19

| Opponent | Matches | W–L | Win rate | Mean score | Mean margin | Errors |
|---|---:|---:|---:|---:|---:|---:|
| Adaptive opening | 16 | 16–0 | 100.0% | 92,643 | +23,542 | 0 |
| Anti-melon | 16 | 14–2 | 87.5% | 94,072 | +22,185 | 0 |
| Arman emulator | 16 | 16–0 | 100.0% | 63,919 | +17,445 | 0 |
| Common-family emulator | 16 | 14–2 | 87.5% | 63,801 | +17,545 | 0 |
| Earlier hybrid counter | 16 | 13–3 | 81.3% | 74,014 | +3,713 | 0 |
| Livestock specialist | 16 | 16–0 | 100.0% | 84,257 | +48,874 | 0 |
| Tetsuya emulator | 16 | 14–2 | 87.5% | 69,732 | +6,228 | 0 |
| **Total** | **112** | **103–9** | **92.0%** | **77,491** | **+19,933** | **0** |

Exact stress manifests: [adaptive opening](../runs/final-vs-adaptive-stress-s12-19/summary.json), [anti-melon](../runs/final-vs-anti_melon-stress-s12-19/summary.json), [Arman](../runs/final-vs-arman-stress-s12-19/summary.json), [common family](../runs/final-vs-common-stress-s12-19/summary.json), [earlier counter](../runs/final-vs-counter-stress-s12-19/summary.json), [livestock](../runs/final-vs-livestock-stress-s12-19/summary.json), and [tetsuya](../runs/final-vs-tetsuya-stress-s12-19/summary.json).

Across holdout and stress artifacts, the final policy was **158–18 over 176 paired-seat games (89.8%)**, with $74,986 mean cash, +$16,229 mean margin, zero runtime errors, and zero ending shed/carried units. Because opponent types overlap and all are local emulators, this combined number is descriptive rather than a calibrated probability of winning a live leaderboard match.

## Conclusions

The replay evidence rejects the old crop-only thesis: every successful leaderboard pattern compounds recurring animals, fertilizer, feed wheat, and premium crops. It also rejects blind imitation. Most leaders crowd the same 2C/2S–melon–strawberry template, and their worst scores occur when both players produce the same premium goods.

The final policy's intended edge is therefore **hybrid service plus residual allocation**: start from a proven five-animal base, preserve feed and terminal discipline, observe the opponent's public capacity, and invest the remaining land/actions in what the market will still pay for. Local emulator results support that design, but live Kaggle episodes remain the authoritative validation.
