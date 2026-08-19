import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from eval.bundle import BUNDLE_FILES, build_bundle


def test_bundle_is_complete_and_loads_outside_the_workspace(tmp_path):
    archive_path = build_bundle(tmp_path / "submission.tar.gz")
    extract_dir = tmp_path / "isolated"
    extract_dir.mkdir()
    with tarfile.open(archive_path, "r:gz") as archive:
        assert set(archive.getnames()) == {path.as_posix() for path in BUNDLE_FILES}
        archive.extractall(extract_dir, filter="data")

    script = """
from kaggle_environments import make
env = make('kaggriculture', configuration={'episodeSteps': 48, 'seed': 19}, debug=True)
env.run(['main.py', 'pass'])
assert env.steps[-1][0].status == 'DONE'
assert env.steps[-1][0].reward is not None
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


def test_bundle_refuses_to_overwrite_an_input_file():
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="must not overwrite"):
        build_bundle(root / "main.py", root=root)
