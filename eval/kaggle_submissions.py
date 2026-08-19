"""Inspect and preserve this team's Kaggriculture submissions.

Authentication is read by the Kaggle client at runtime.  This module never
stores or prints credentials, and a prior upload is downloaded atomically only
to the explicit output path supplied by the caller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


def _enum_name(value: object) -> str:
    return getattr(value, "name", str(value).rsplit(".", 1)[-1])


def summarize_episodes(submission_id: int, episodes: Iterable[Any]) -> dict[str, Any]:
    """Return the rated public record for one submission.

    Validation episodes and public self-play are listed as excluded evidence,
    but do not affect the rated match record.
    """

    matches: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    wins = losses = ties = 0

    for episode in episodes:
        episode_type = _enum_name(episode.type)
        agents = list(episode.agents or [])
        targets = [agent for agent in agents if int(agent.submission_id) == submission_id]
        episode_id = int(episode.id)

        if episode_type != "EPISODE_TYPE_PUBLIC":
            excluded.append({"episode_id": episode_id, "reason": episode_type})
            continue
        if len(targets) != 1 or len(agents) != 2:
            excluded.append({"episode_id": episode_id, "reason": "self-or-ambiguous"})
            continue

        target = targets[0]
        opponent = agents[1 - int(target.index)] if int(target.index) in (0, 1) else next(
            agent for agent in agents if agent is not target
        )
        target_reward = float(target.reward)
        opponent_reward = float(opponent.reward)
        if target_reward > opponent_reward:
            result = "win"
            wins += 1
        elif target_reward < opponent_reward:
            result = "loss"
            losses += 1
        else:
            result = "tie"
            ties += 1
        matches.append(
            {
                "episode_id": episode_id,
                "opponent": str(opponent.team_name),
                "seat": int(target.index),
                "score": target_reward,
                "opponent_score": opponent_reward,
                "result": result,
            }
        )

    rated_matches = wins + losses + ties
    return {
        "submission_id": submission_id,
        "rated_matches": rated_matches,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": wins / rated_matches if rated_matches else 0.0,
        "matches": sorted(matches, key=lambda row: row["episode_id"]),
        "excluded_episodes": sorted(excluded, key=lambda row: row["episode_id"]),
    }


def _authenticated_api():
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    return api


def snapshot_submission(competition: str, submission_id: int) -> dict[str, Any]:
    """Fetch current rating metadata and the complete public episode record."""

    api = _authenticated_api()
    submissions = api.competition_submissions(competition)
    submission = next((item for item in submissions if int(item.ref) == submission_id), None)
    if submission is None:
        raise ValueError(f"submission {submission_id} was not found in {competition}")
    result = summarize_episodes(submission_id, api.competition_list_episodes(submission_id))
    result.update(
        {
            "competition": competition,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "description": str(submission.description),
            "submitted_at": str(submission.date),
            "status": str(submission.status),
            "public_score": float(submission.public_score),
        }
    )
    return result


def _safe_tar_members(path: Path) -> list[str]:
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
    for name in names:
        member = PurePosixPath(name)
        if member.is_absolute() or ".." in member.parts:
            raise ValueError(f"unsafe archive member: {name}")
    return names


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_submission(submission_id: int, output: Path) -> dict[str, Any]:
    """Download an exact prior upload without exposing its signed URL."""

    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    api = _authenticated_api()
    from kagglesdk.competitions.types.competition_api_service import (
        ApiDownloadSubmissionRequest,
    )

    request = ApiDownloadSubmissionRequest()
    request.submission_id = submission_id
    with api.build_kaggle_client() as kaggle:
        redirect = kaggle.competitions.competition_api_client.download_submission(request)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{submission_id}-", suffix=".tmp", dir=output.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with urllib.request.urlopen(redirect.url, timeout=60) as response:
                shutil.copyfileobj(response, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        members = _safe_tar_members(temporary_path)
        digest = sha256_file(temporary_path)
        os.replace(temporary_path, output)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return {
        "submission_id": submission_id,
        "output": str(output),
        "sha256": digest,
        "bytes": output.stat().st_size,
        "members": members,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="print current rating and episode record")
    snapshot.add_argument("submission_id", type=int)
    snapshot.add_argument("--competition", default="kaggriculture")
    snapshot.add_argument(
        "--summary-only",
        action="store_true",
        help="omit per-episode rows while retaining counts",
    )

    download = subparsers.add_parser("download", help="preserve an exact uploaded archive")
    download.add_argument("submission_id", type=int)
    download.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "snapshot":
        result = snapshot_submission(args.competition, args.submission_id)
        if args.summary_only:
            result.pop("matches", None)
            result.pop("excluded_episodes", None)
    else:
        result = download_submission(args.submission_id, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
