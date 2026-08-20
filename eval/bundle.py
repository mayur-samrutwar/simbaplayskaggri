"""Build the promoted agent's local, multi-file submission archive.

This module performs no network request and never submits the resulting file.
"""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


BUNDLE_FILES = (
    Path("main.py"),
    Path("candidates/__init__.py"),
    Path("candidates/live_archetypes.py"),
    Path("candidates/resilient_portfolio.py"),
    Path("candidates/throughput_portfolio.py"),
)


def build_bundle(output: Path, root: Path | None = None) -> Path:
    root = (root or Path(__file__).resolve().parents[1]).resolve()
    output = output.resolve()
    missing = [str(path) for path in BUNDLE_FILES if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError(f"bundle inputs missing: {', '.join(missing)}")
    inputs = {(root / relative).resolve() for relative in BUNDLE_FILES}
    if output in inputs:
        raise ValueError("bundle output must not overwrite a source file")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for relative in BUNDLE_FILES:
            archive.add(root / relative, arcname=relative.as_posix(), recursive=False)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/submission.tar.gz"))
    args = parser.parse_args()
    output = build_bundle(args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
