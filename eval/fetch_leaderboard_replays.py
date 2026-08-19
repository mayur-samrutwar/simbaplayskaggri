"""Collect recent public simulation replays for Kaggle submission IDs.

The Kaggle CLI handles authentication.  This wrapper adds deterministic
selection, caching, deduplication, a manifest, and conservative pacing so the
internal episode service is not queried in a burst.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KAGGLE = ROOT / ".venv" / "bin" / "kaggle"


def _run(args: list[str], retries: int = 4) -> str:
    """Run Kaggle CLI with bounded exponential backoff."""
    for attempt in range(retries):
        result = subprocess.run(
            [str(KAGGLE), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        if attempt + 1 == retries:
            raise RuntimeError(
                f"Kaggle command failed after {retries} attempts: "
                f"{' '.join(args)}\n{result.stderr.strip()}"
            )
        time.sleep(5 * (2**attempt))
    raise AssertionError("unreachable")


def recent_episode_ids(submission_id: int, limit: int) -> list[int]:
    raw = _run(
        [
            "competitions",
            "episodes",
            str(submission_id),
            "--format",
            "json",
            "--quiet",
        ]
    )
    episodes = json.loads(raw)
    selected = [
        int(episode["id"])
        for episode in episodes
        if str(episode.get("state", "")).endswith("COMPLETED")
        and str(episode.get("type", "")).endswith("PUBLIC")
    ]
    return selected[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("submission_ids", nargs="+", type=int)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "replays" / "leaderboard",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "limit_per_submission": args.limit,
        "submissions": {},
    }
    unique_ids: list[int] = []
    seen: set[int] = set()

    for index, submission_id in enumerate(args.submission_ids, start=1):
        episode_ids = recent_episode_ids(submission_id, args.limit)
        manifest["submissions"][str(submission_id)] = episode_ids
        for episode_id in episode_ids:
            if episode_id not in seen:
                seen.add(episode_id)
                unique_ids.append(episode_id)
        print(
            f"episodes {index}/{len(args.submission_ids)}: "
            f"submission {submission_id} -> {len(episode_ids)}",
            flush=True,
        )
        time.sleep(args.delay)

    for index, episode_id in enumerate(unique_ids, start=1):
        target = output / f"episode-{episode_id}-replay.json"
        if not target.exists():
            _run(
                [
                    "competitions",
                    "replay",
                    str(episode_id),
                    "--path",
                    str(output),
                    "--quiet",
                ]
            )
            time.sleep(args.delay)
        print(
            f"replay {index}/{len(unique_ids)}: episode {episode_id}",
            flush=True,
        )

    manifest["unique_episode_ids"] = unique_ids
    manifest["unique_episode_count"] = len(unique_ids)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
