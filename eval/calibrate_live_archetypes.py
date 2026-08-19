"""Calibrate the independent live-archetype regression opponents.

Examples:
    python -m eval.calibrate_live_archetypes --opponent main.py --seeds 20:24
    python -m eval.calibrate_live_archetypes --opponent starter --seeds 12,13

The output reports both competitive results and the absolute-score frequency
above 90k.  Absolute score matters because a high win rate against a weak local
agent was the principal failure mode of the original emulator suite.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from eval.tournament import MatchSpec, _run_match, parse_seeds, summarize


ARCHETYPES = {
    "melon_strawberry": "candidates/live_melon_strawberry.py",
    "strawberry": "candidates/live_strawberry.py",
    "milk": "candidates/live_milk.py",
    "tomato_goose": "candidates/live_tomato_goose.py",
}


def run_suite(opponent: str, seeds: list[int], episode_steps: int = 720):
    report = {}
    for name, candidate in ARCHETYPES.items():
        rows = [
            _run_match(MatchSpec(seed, candidate, opponent, seat, episode_steps))
            for seed in seeds
            for seat in (0, 1)
        ]
        summary = summarize(rows)
        valid_scores = [row.candidate_money for row in rows if not row.error]
        summary.update(
            {
                "median_candidate_money": statistics.median(valid_scores) if valid_scores else 0.0,
                "scores_at_least_90000": sum(score >= 90_000 for score in valid_scores),
                "fraction_at_least_90000": (
                    sum(score >= 90_000 for score in valid_scores) / len(valid_scores)
                    if valid_scores
                    else 0.0
                ),
                "min_candidate_money": min(valid_scores) if valid_scores else 0.0,
                "max_candidate_money": max(valid_scores) if valid_scores else 0.0,
            }
        )
        report[name] = summary
    return report


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opponent", default="main.py", help="agent path or built-in opponent")
    parser.add_argument("--seeds", default="20:24", help="START:STOP[:STEP] or comma-separated seeds")
    parser.add_argument("--episode-steps", type=int, default=720)
    return parser


def main():
    args = build_parser().parse_args()
    seeds = parse_seeds(args.seeds)
    if not seeds:
        raise SystemExit("at least one seed is required")
    opponent = args.opponent
    if opponent not in {"pass", "random", "starter"}:
        opponent = str(Path(opponent).resolve())
    report = run_suite(opponent, seeds, args.episode_steps)
    print(json.dumps({"opponent": opponent, "seeds": seeds, "archetypes": report}, indent=2))
    return 1 if any(row["errors"] for row in report.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
