"""Run the shared fixed-shop promotion suite from the command line."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median

from eval.scenarios import run_fixed_shop_scenario
from eval.tournament import BUILT_INS, parse_seeds


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {
    "no_shops": (),
    "balanced_unique": (
        "BAKERY",
        "PIZZA_SHOP",
        "BRUNCH_SPOT",
        "YARN_STORE",
        "ICE_CREAM_SHOP",
        "PET_CAFE",
        "SMOOTHIE_SHOP",
        "FARMERS_MARKET",
    ),
    "wool": ("YARN_STORE",) * 8,
    "egg_wheat": ("BAKERY", "BRUNCH_SPOT") * 4,
    "milk_berry": (
        "ICE_CREAM_SHOP",
        "SMOOTHIE_SHOP",
        "PIZZA_SHOP",
        "ICE_CREAM_SHOP",
        "SMOOTHIE_SHOP",
        "PIZZA_SHOP",
        "ICE_CREAM_SHOP",
        "SMOOTHIE_SHOP",
    ),
    "crop_market": ("FARMERS_MARKET",) * 8,
    "carrot": ("PET_CAFE",) * 8,
}


def _portable_reference(reference: str) -> str:
    if reference in BUILT_INS:
        return reference
    path = Path(reference)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(reference: str) -> str | None:
    if reference in BUILT_INS:
        return None
    path = Path(reference)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summarize(rows):
    margins = [row.candidate_money - row.opponent_money for row in rows]
    wins = sum(row.outcome == "win" for row in rows)
    losses = sum(row.outcome == "loss" for row in rows)
    ties = sum(row.outcome == "tie" for row in rows)
    errors = sum(
        row.candidate_status != "DONE" or row.opponent_status != "DONE"
        for row in rows
    )
    return {
        "matches": len(rows),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": wins / len(rows) if rows else 0.0,
        "mean_candidate_money": mean(row.candidate_money for row in rows),
        "mean_opponent_money": mean(row.opponent_money for row in rows),
        "mean_margin": mean(margins),
        "median_margin": median(margins),
        "min_margin": min(margins),
        "max_margin": max(margins),
        "errors": errors,
    }


def run_suite(
    candidate: str,
    opponent: str,
    *,
    seeds: list[int],
    episode_steps: int = 720,
):
    all_rows = []
    scenario_rows = []
    raw_rows = []
    for name, shops in SCENARIOS.items():
        rows = []
        for seed in seeds:
            for seat in (0, 1):
                result = run_fixed_shop_scenario(
                    candidate,
                    opponent,
                    seed=seed,
                    shops=shops,
                    candidate_seat=seat,
                    episode_steps=episode_steps,
                )
                rows.append(result)
                all_rows.append(result)
                raw = asdict(result)
                raw["scenario"] = name
                raw["margin"] = result.candidate_money - result.opponent_money
                raw_rows.append(raw)
        scenario_rows.append(
            {
                "scenario": name,
                "shops": list(shops),
                **_summarize(rows),
            }
        )
    return {
        "candidate": _portable_reference(candidate),
        "candidate_sha256": _sha256(candidate),
        "opponent": _portable_reference(opponent),
        "opponent_sha256": _sha256(opponent),
        "seeds": seeds,
        "paired_seats": True,
        "episode_steps": episode_steps,
        "summary": {
            "scenarios": len(SCENARIOS),
            **_summarize(all_rows),
        },
        "scenarios": scenario_rows,
        "matches": raw_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--opponent", required=True)
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--episode-steps", type=int, default=720)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run_suite(
        args.candidate,
        args.opponent,
        seeds=parse_seeds(args.seeds),
        episode_steps=args.episode_steps,
    )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "summary.json"
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
