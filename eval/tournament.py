"""Run deterministic, paired-seat Kaggriculture tournaments locally.

Examples:
    python -m eval.tournament --candidate main.py --opponent starter --seeds 0:8
    python -m eval.tournament --candidate candidates/crop.py \
        --opponent candidates/livestock.py --seeds 20,21,22
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from kaggle_environments import make


BUILT_INS = {"pass", "random", "starter"}


@dataclass(frozen=True)
class MatchSpec:
    seed: int
    candidate: str
    opponent: str
    candidate_seat: int
    episode_steps: int = 720


@dataclass
class MatchResult:
    seed: int
    candidate_seat: int
    candidate_money: float
    opponent_money: float
    candidate_status: str
    opponent_status: str
    outcome: str
    elapsed_seconds: float
    shops: str
    error: str = ""
    ending_shed_units: int = 0
    ending_carried_units: int = 0
    ending_plants: int = 0
    ending_animals: int = 0
    ending_weeds: int = 0


def _agent_ref(value: str) -> str:
    if value in BUILT_INS:
        return value
    return str(Path(value).resolve())


def _run_match(spec: MatchSpec) -> MatchResult:
    candidate = _agent_ref(spec.candidate)
    opponent = _agent_ref(spec.opponent)
    agents = [opponent, candidate] if spec.candidate_seat else [candidate, opponent]
    started = time.perf_counter()
    try:
        env = make(
            "kaggriculture",
            configuration={"episodeSteps": spec.episode_steps, "seed": spec.seed},
            debug=True,
        )
        env.run(agents)
        final = env.steps[-1]
        c_state = final[spec.candidate_seat]
        o_state = final[1 - spec.candidate_seat]
        c_money = float(c_state.reward or 0.0)
        o_money = float(o_state.reward or 0.0)
        c_status = str(c_state.status)
        o_status = str(o_state.status)
        status_error = "" if c_status == "DONE" else f"candidate ended with status {c_status}"
        if c_status != "DONE":
            outcome = "loss"
        elif o_status != "DONE":
            outcome = "win"
        else:
            outcome = "win" if c_money > o_money else "loss" if c_money < o_money else "tie"
        shops = final[0].observation.get("town", {}).get("unlocked_shops", [])
        private = c_state.observation.get("private", {})
        shed_units = sum(int(value) for value in private.get("shed", {}).values())
        carried_units = sum(
            int(value)
            for inventory in private.get("inventories", [])
            for value in inventory.values()
        )
        tiles = c_state.observation["farms"][spec.candidate_seat]["tiles"]
        flat_tiles = [tile for row in tiles for tile in row]
        plants = sum(isinstance(tile, dict) and tile.get("kind") == "PLANT" for tile in flat_tiles)
        animals = sum(isinstance(tile, dict) and "animal" in tile for tile in flat_tiles)
        weeds = sum(isinstance(tile, dict) and tile.get("kind") == "WEED" for tile in flat_tiles)
        return MatchResult(
            seed=spec.seed,
            candidate_seat=spec.candidate_seat,
            candidate_money=c_money,
            opponent_money=o_money,
            candidate_status=c_status,
            opponent_status=o_status,
            outcome=outcome,
            elapsed_seconds=time.perf_counter() - started,
            shops="|".join(shops),
            ending_shed_units=shed_units,
            ending_carried_units=carried_units,
            ending_plants=plants,
            ending_animals=animals,
            ending_weeds=weeds,
            error=status_error,
        )
    except Exception as exc:  # pragma: no cover - exercised by broken agents
        return MatchResult(
            seed=spec.seed,
            candidate_seat=spec.candidate_seat,
            candidate_money=0.0,
            opponent_money=0.0,
            candidate_status="ERROR",
            opponent_status="UNKNOWN",
            outcome="loss",
            elapsed_seconds=time.perf_counter() - started,
            shops="",
            error=f"{type(exc).__name__}: {exc}",
        )


def parse_seeds(raw: str) -> list[int]:
    """Parse `0:8`, `0:20:2`, or comma-separated integer seeds."""
    raw = raw.strip()
    if ":" in raw and "," not in raw:
        parts = [int(part) for part in raw.split(":")]
        if len(parts) == 2:
            start, stop = parts
            step = 1
        elif len(parts) == 3:
            start, stop, step = parts
        else:
            raise ValueError("seed range must be START:STOP or START:STOP:STEP")
        return list(range(start, stop, step))
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def summarize(results: Iterable[MatchResult]) -> dict[str, object]:
    rows = list(results)
    counts = {name: sum(row.outcome == name for row in rows) for name in ("win", "loss", "tie")}
    valid = [row for row in rows if not row.error]
    margins = [row.candidate_money - row.opponent_money for row in valid]
    candidate_money = [row.candidate_money for row in valid]
    total = len(rows)
    return {
        "matches": total,
        "wins": counts["win"],
        "losses": counts["loss"],
        "ties": counts["tie"],
        "win_rate": counts["win"] / total if total else 0.0,
        "non_loss_rate": (counts["win"] + counts["tie"]) / total if total else 0.0,
        "mean_candidate_money": statistics.fmean(candidate_money) if candidate_money else 0.0,
        "mean_margin": statistics.fmean(margins) if margins else 0.0,
        "median_margin": statistics.median(margins) if margins else 0.0,
        "errors": sum(bool(row.error) for row in rows),
        "mean_ending_shed_units": statistics.fmean(row.ending_shed_units for row in valid) if valid else 0.0,
        "mean_ending_carried_units": statistics.fmean(row.ending_carried_units for row in valid) if valid else 0.0,
        "elapsed_seconds": sum(row.elapsed_seconds for row in rows),
    }


def _write_results(output_dir: Path, results: list[MatchResult], summary: dict[str, object], args: argparse.Namespace) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate": str(Path(args.candidate).resolve()) if args.candidate not in BUILT_INS else args.candidate,
        "opponent": str(Path(args.opponent).resolve()) if args.opponent not in BUILT_INS else args.opponent,
        "seeds": parse_seeds(args.seeds),
        "episode_steps": args.episode_steps,
        "workers": args.workers,
        "summary": summary,
    }
    (output_dir / "summary.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="main.py", help="agent path or built-in name")
    parser.add_argument("--opponent", default="starter", help="agent path or built-in name")
    parser.add_argument("--seeds", default="0:8", help="START:STOP[:STEP] or comma list")
    parser.add_argument("--episode-steps", type=int, default=720)
    # One worker is the portable default. Some macOS sandboxes deny the
    # semaphore sysconf call used by ProcessPoolExecutor.
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path, help="optional output directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    seeds = parse_seeds(args.seeds)
    if not seeds:
        raise SystemExit("at least one seed is required")
    specs = [
        MatchSpec(seed, args.candidate, args.opponent, seat, args.episode_steps)
        for seed in seeds
        for seat in (0, 1)
    ]
    results: list[MatchResult] = []
    if args.workers == 1:
        results = [_run_match(spec) for spec in specs]
    else:
        try:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(_run_match, spec): spec for spec in specs}
                for future in as_completed(futures):
                    results.append(future.result())
        except PermissionError:
            print("process workers unavailable in this sandbox; falling back to one worker")
            results = [_run_match(spec) for spec in specs]
    results.sort(key=lambda row: (row.seed, row.candidate_seat))
    summary = summarize(results)
    print(json.dumps(summary, indent=2))
    for result in results:
        if result.error:
            print(f"seed={result.seed} seat={result.candidate_seat} ERROR {result.error}")
    if args.output:
        _write_results(args.output, results, summary, args)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
