from __future__ import annotations

import hashlib
import tarfile
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.kaggle_submissions import (
    _safe_tar_members,
    download_submission,
    sha256_file,
    summarize_episodes,
)


class EpisodeType(Enum):
    EPISODE_TYPE_PUBLIC = 1
    EPISODE_TYPE_VALIDATION = 4


def _agent(submission_id, index, reward, team_name):
    return SimpleNamespace(
        submission_id=submission_id,
        index=index,
        reward=float(reward),
        team_name=team_name,
    )


def _episode(episode_id, episode_type, agents):
    return SimpleNamespace(id=episode_id, type=episode_type, agents=agents)


def test_summarize_episodes_excludes_validation_and_self_play():
    submission_id = 123
    episodes = [
        _episode(
            10,
            EpisodeType.EPISODE_TYPE_PUBLIC,
            [_agent(999, 0, 50, "rival"), _agent(submission_id, 1, 80, "astro")],
        ),
        _episode(
            11,
            EpisodeType.EPISODE_TYPE_PUBLIC,
            [_agent(submission_id, 0, 40, "astro"), _agent(888, 1, 60, "other")],
        ),
        _episode(
            12,
            EpisodeType.EPISODE_TYPE_VALIDATION,
            [_agent(submission_id, 0, 70, "astro"), _agent(submission_id, 1, 65, "astro")],
        ),
        _episode(
            13,
            EpisodeType.EPISODE_TYPE_PUBLIC,
            [_agent(submission_id, 0, 70, "astro"), _agent(submission_id, 1, 65, "astro")],
        ),
    ]

    result = summarize_episodes(submission_id, episodes)

    assert (result["wins"], result["losses"], result["ties"]) == (1, 1, 0)
    assert result["rated_matches"] == 2
    assert result["win_rate"] == 0.5
    assert [row["result"] for row in result["matches"]] == ["win", "loss"]
    assert result["excluded_episodes"] == [
        {"episode_id": 12, "reason": "EPISODE_TYPE_VALIDATION"},
        {"episode_id": 13, "reason": "self-or-ambiguous"},
    ]


def test_download_refuses_to_overwrite_before_authentication(tmp_path):
    target = tmp_path / "existing.tar.gz"
    target.write_bytes(b"keep")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        download_submission(123, target)

    assert target.read_bytes() == b"keep"


def test_archive_path_validation_and_sha256(tmp_path):
    safe = tmp_path / "safe.tar.gz"
    with tarfile.open(safe, "w:gz") as archive:
        info = tarfile.TarInfo("main.py")
        info.size = 0
        archive.addfile(info)
    assert _safe_tar_members(safe) == ["main.py"]
    assert sha256_file(safe) == hashlib.sha256(safe.read_bytes()).hexdigest()

    unsafe = tmp_path / "unsafe.tar.gz"
    with tarfile.open(unsafe, "w:gz") as archive:
        info = tarfile.TarInfo("../secret")
        info.size = 0
        archive.addfile(info)
    with pytest.raises(ValueError, match="unsafe archive member"):
        _safe_tar_members(unsafe)
