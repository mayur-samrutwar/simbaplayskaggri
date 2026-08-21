"""Evaluate a candidate against each audited leaderboard bot's action traces.

``replay_trace_tournament`` replaces one named player with the candidate and
replays the other player's public actions.  This driver applies that primitive
to the 100 submission/episode references in the leaderboard audit: for each
target bot, the candidate replaces that bot's historical opponent, leaving the
target bot as the trace agent.

The traces are not private source code and cannot reproduce reactive decisions,
but they are independent, live-derived schedules with realistic market timing.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from eval.replay_trace_tournament import TraceResult, run_trace


def load_cases(
    manifest_path: Path,
    analysis_path: Path,
    replay_dir: Path,
    submission_ids: set[str] | None = None,
    limit_per_team: int | None = None,
) -> list[tuple[str, str, Path]]:
    """Return ``(submission_id, replacement_team, replay_path)`` cases."""

    manifest = json.loads(manifest_path.read_text())
    analysis = json.loads(analysis_path.read_text())
    target_names = {
        str(key): str(value) for key, value in analysis["target_names"].items()
    }
    cases = []
    for submission_id, episode_ids in manifest["submissions"].items():
        submission_id = str(submission_id)
        if submission_ids and submission_id not in submission_ids:
            continue
        target = target_names[submission_id]
        selected = episode_ids[:limit_per_team] if limit_per_team else episode_ids
        for episode_id in selected:
            replay_path = replay_dir / f"episode-{int(episode_id)}-replay.json"
            replay = json.loads(replay_path.read_text())
            names = list(replay.get("info", {}).get("TeamNames", []))
            if len(names) != 2 or target not in names:
                raise ValueError(
                    f"{replay_path}: expected two teams including {target!r}, got {names!r}"
                )
            replacement_team = names[1 - names.index(target)]
            cases.append((submission_id, replacement_team, replay_path))
    return cases


def _summary(results: list[TraceResult]) -> dict[str, float | int]:
    valid = [result for result in results if not result.error]
    return {
        "matches": len(results),
        "wins": sum(result.outcome == "win" for result in results),
        "losses": sum(result.outcome == "loss" for result in results),
        "ties": sum(result.outcome == "tie" for result in results),
        "errors": sum(bool(result.error) for result in results),
        "win_rate": (
            sum(result.outcome == "win" for result in valid) / len(valid)
            if valid
            else 0.0
        ),
        "mean_candidate_money": (
            statistics.fmean(result.candidate_money for result in valid)
            if valid
            else 0.0
        ),
        "mean_trace_money": (
            statistics.fmean(result.opponent_money for result in valid)
            if valid
            else 0.0
        ),
        "mean_margin": (
            statistics.fmean(result.margin for result in valid) if valid else 0.0
        ),
    }


def run_suite(
    candidate: Path,
    cases: list[tuple[str, str, Path]],
    target_names: dict[str, str],
    save_replay_dir: Path | None = None,
) -> dict:
    rows = []
    grouped: dict[str, list[TraceResult]] = defaultdict(list)
    for submission_id, replacement_team, replay_path in cases:
        result = run_trace(candidate, replay_path, replacement_team, save_replay_dir)
        grouped[submission_id].append(result)
        rows.append(
            asdict(result)
            | {
                "margin": result.margin,
                "submission_id": int(submission_id),
                "trace_team": target_names[submission_id],
            }
        )
    return {
        "overall": _summary([result for group in grouped.values() for result in group]),
        "teams": {
            submission_id: {"team": target_names[submission_id], **_summary(results)}
            for submission_id, results in grouped.items()
        },
        "matches": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path("replays/leaderboard/manifest.json")
    )
    parser.add_argument(
        "--analysis", type=Path, default=Path("replays/leaderboard/analysis.json")
    )
    parser.add_argument("--replay-dir", type=Path, default=Path("replays/leaderboard"))
    parser.add_argument("--submission", action="append", default=[])
    parser.add_argument("--limit-per-team", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--save-replays", type=Path)
    args = parser.parse_args()

    analysis = json.loads(args.analysis.read_text())
    target_names = {
        str(key): str(value) for key, value in analysis["target_names"].items()
    }
    cases = load_cases(
        args.manifest,
        args.analysis,
        args.replay_dir,
        set(args.submission) or None,
        args.limit_per_team,
    )
    if not cases:
        raise SystemExit("no leaderboard trace cases selected")
    payload = run_suite(args.candidate, cases, target_names, args.save_replays)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    return 1 if payload["overall"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
