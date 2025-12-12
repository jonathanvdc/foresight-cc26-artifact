#!/usr/bin/env python3
"""LIAR experiment module.

This module is designed to be imported by the artifact's top-level driver
(e.g., scripts/eval.py). It only runs the LIAR experiments and stores their raw
outputs in a stable directory layout.

Outputs (relative to out_root):
  results/liar/
    baseline/
    foresight/

Baseline (cwd = results/liar/baseline):
  python3 liar/src/scripts/liar-evaluation/evaluate_all.py -t300 --limit-steps

Foresight (cwd = results/liar/foresight):
  1) python3 ... --engine=foresight --foresight-thread-counts=1-8 stencil2d --optimize-only
  2) python3 ... --engine=foresight --foresight-thread-counts=1

Aggregation/plotting is intentionally not handled here yet.
"""

from __future__ import annotations

import os
from pathlib import Path

from common import eprint, ensure_dir, run_cmd


EXPERIMENT_NAME = "liar"


def default_repo_root() -> Path:
    """Default location of the LIAR repository (relative to the artifact root)."""
    return Path("liar")


def _timeout_seconds(timeout_seconds: int | None) -> int:
    """Resolve timeout seconds from an explicit value or env var."""
    if timeout_seconds is not None:
        return timeout_seconds
    # Optional convenience override for CI / reviewers.
    v = os.environ.get("LIAR_TIMEOUT_SECONDS")
    if v is None:
        return 300
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"Invalid LIAR_TIMEOUT_SECONDS: {v!r}")


def run(
    *,
    out_root: Path,
    repo_root: Path | None = None,
    timeout_seconds: int | None = None,
) -> None:
    """Run the LIAR experiments.

    Args:
        out_root: Root output directory (e.g., Path('/results')).
        repo_root: Path to the LIAR repo directory (default: Path('liar')).
        timeout_seconds: Timeout for LIAR's optimizer (passed as -tNNN).
            Defaults to env var LIAR_TIMEOUT_SECONDS if set, else 300.
    """

    repo_root = default_repo_root() if repo_root is None else repo_root
    timeout = _timeout_seconds(timeout_seconds)

    liar_dir = out_root / "results" / "liar"
    baseline_dir = liar_dir / "baseline"
    foresight_dir = liar_dir / "foresight"

    ensure_dir(baseline_dir)
    ensure_dir(foresight_dir)

    # Path to the LIAR evaluation script.
    eval_py = repo_root / "src" / "scripts" / "liar-evaluation" / "evaluate_all.py"
    if not eval_py.exists():
        raise FileNotFoundError(
            f"Could not find LIAR evaluation script at: {eval_py}\n"
            f"Hint: ensure the LIAR repo is available at: {repo_root}"
        )

    eprint(f"[{EXPERIMENT_NAME}] Writing results under: {liar_dir}")

    # Baseline (legacy engine).
    run_cmd(
        [
            "python3",
            "-u",
            str(eval_py),
            f"-t{timeout}",
            "--limit-steps",
        ],
        cwd=baseline_dir,
        capture_stdout=False,
    )

    # Foresight: (1) optimize-only stencil2d across 1-8 threads.
    run_cmd(
        [
            "python3",
            "-u",
            str(eval_py),
            f"-t{timeout}",
            "--limit-steps",
            "--engine=foresight",
            "--foresight-thread-counts=1-8",
            "--optimize-only",
            "stencil2d",
        ],
        cwd=foresight_dir,
        capture_stdout=False,
    )

    # Foresight: (2) full run at 1 thread (includes running kernels).
    run_cmd(
        [
            "python3",
            "-u",
            str(eval_py),
            f"-t{timeout}",
            "--limit-steps",
            "--engine=foresight",
            "--foresight-thread-counts=1",
        ],
        cwd=foresight_dir,
        capture_stdout=False,
    )
