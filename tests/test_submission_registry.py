from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path, PurePosixPath

import pytest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "submissions" / "registry.toml"


def _registry():
    with REGISTRY_PATH.open("rb") as handle:
        return tomllib.load(handle)


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_registry_scores_records_and_ranks_are_consistent():
    registry = _registry()
    submissions = registry["submissions"]
    assert [row["id"] for row in submissions] == [55623462, 55625688, 55631403]
    assert len({row["id"] for row in submissions}) == len(submissions)

    ranked = sorted(submissions, key=lambda row: row["current_rating"], reverse=True)
    assert [row["rating_rank"] for row in ranked] == [1, 2, 3]
    assert registry["current_rating_leader"] == ranked[0]["id"]
    assert registry["established_baseline"] == 55625688

    for row in submissions:
        assert row["rated_matches"] == row["wins"] + row["losses"] + row["ties"]
        assert row["win_rate"] == pytest.approx(
            row["wins"] / row["rated_matches"] if row["rated_matches"] else 0.0
        )
        assert row["peak_observed_rating"] >= row["current_rating"]
        latest = row["observations"][-1]
        assert latest["rating"] == row["current_rating"]
        assert latest["rated_matches"] == row["rated_matches"]
        assert latest["wins"] == row["wins"]
        assert latest["losses"] == row["losses"]
        assert latest["ties"] == row["ties"]


def test_exact_rollback_archives_are_hash_verified_and_safe():
    forbidden_names = {"access_token", "kaggle.json", ".env"}
    forbidden_content = (b"KGAT_", b"KAGGLE_API_TOKEN")

    for row in _registry()["submissions"]:
        path = ROOT / row["artifact_path"]
        assert path.is_file()
        assert path.stat().st_size == row["artifact_bytes"]
        assert _sha256(path) == row["artifact_sha256"]
        assert row["rollback_fidelity"] == "byte-exact-kaggle-upload"

        with tarfile.open(path, "r:gz") as archive:
            assert archive.getnames() == row["bundle_files"]
            for member in archive.getmembers():
                member_path = PurePosixPath(member.name)
                assert not member_path.is_absolute()
                assert ".." not in member_path.parts
                assert not (forbidden_names & set(member_path.parts))
                if member.isfile():
                    content = archive.extractfile(member).read()
                    assert all(marker not in content for marker in forbidden_content)


@pytest.mark.parametrize("submission_id", [55623462, 55625688, 55631403])
def test_each_exact_archive_loads_outside_the_workspace(tmp_path, submission_id):
    row = next(item for item in _registry()["submissions"] if item["id"] == submission_id)
    extract_dir = tmp_path / str(submission_id)
    extract_dir.mkdir()
    with tarfile.open(ROOT / row["artifact_path"], "r:gz") as archive:
        archive.extractall(extract_dir, filter="data")

    script = """
from kaggle_environments import make
env = make('kaggriculture', configuration={'episodeSteps': 48, 'seed': 23}, debug=True)
env.run(['main.py', 'pass'])
final = env.steps[-1][0]
assert final.status == 'DONE'
assert final.reward is not None
"""
    clean_env = dict(os.environ)
    clean_env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=extract_dir,
        env=clean_env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
