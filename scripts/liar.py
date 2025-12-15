#!/usr/bin/env python3
"""LIAR experiment module.

Outputs (relative to out_root):
  liar/
    baseline/
    foresight/

Baseline (cwd = results/liar/baseline):
  python3 liar/src/scripts/liar-evaluation/evaluate_all.py -t300 --limit-steps

Foresight (cwd = results/liar/foresight):
  1) python3 ... --engine=foresight --foresight-thread-counts=1-8 stencil2d --optimize-only
  2) python3 ... --engine=foresight --foresight-thread-counts=1
"""

from __future__ import annotations

import os
from pathlib import Path

from common import eprint, ensure_dir, run_cmd
import csv


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
    run_experiments(out_root=out_root, repo_root=repo_root, timeout_seconds=timeout_seconds)
    process_results(out_root=out_root)


def run_experiments(
    *,
    out_root: Path,
    repo_root: Path | None = None,
    timeout_seconds: int | None = None,
) -> None:
    repo_root = default_repo_root() if repo_root is None else repo_root
    timeout = _timeout_seconds(timeout_seconds)

    liar_dir = out_root / "liar"
    baseline_dir = liar_dir / "baseline"
    foresight_dir = liar_dir / "foresight"
    foresight_parallel_dir = liar_dir / "foresight-parallel"

    ensure_dir(baseline_dir)
    ensure_dir(foresight_dir)
    ensure_dir(foresight_parallel_dir)

    # Path to the LIAR evaluation script.
    eval_py = (repo_root / "src" / "scripts" / "liar-evaluation" / "evaluate_all.py").resolve()
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
    foresight_threads_env = os.environ.get("FORESIGHT_THREAD_COUNTS")
    if foresight_threads_env:
        # Convert space-separated list (e.g. "1 2 4 8") to CLI format "1,2,4,8"
        foresight_threads = ",".join(foresight_threads_env.split())
    else:
        foresight_threads = "1-8"
    run_cmd(
        [
            "python3",
            "-u",
            str(eval_py),
            f"-t{timeout}",
            "--limit-steps",
            "--engine=foresight",
            f"--foresight-thread-counts={foresight_threads}",
            "--optimize-only",
            "stencil2d",
        ],
        cwd=foresight_parallel_dir,
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


def process_results(*, out_root: Path) -> None:
    liar_dir = out_root / "liar"
    table1_path = liar_dir / "table-1.csv"
    table1_rows = compute_table1_rows(out_root=out_root)
    # Deterministic order.
    table1_rows.sort(key=lambda r: r.get("kernel", ""))

    with table1_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["kernel", "liar_solution", "intuition_solution", "speedup"],
        )
        writer.writeheader()
        writer.writerows(table1_rows)

    eprint(f"[{EXPERIMENT_NAME}] Wrote Table 1 to: {table1_path}")


# Helper functions to reproduce Table 1 from the paper.
def _read_csv_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    """Read a CSV file into a dict keyed by a column value."""
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV: {path}")

    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or key not in reader.fieldnames:
            raise ValueError(f"CSV {path} missing required column: {key}")
        out: dict[str, dict[str, str]] = {}
        for row in reader:
            k = (row.get(key) or "").strip()
            if not k:
                continue
            out[k] = row
        return out


def _parse_float(value: str, *, ctx: str) -> float:
    try:
        return float(value)
    except Exception as ex:
        raise ValueError(f"Could not parse float for {ctx}: {value!r}") from ex


def _format_speedup_x(ratio: float) -> str:
    """Format the Table 1 speedup column.

    The paper reports Sp. in the range 1x.. We round to two
    decimal places.
    """
    if ratio != ratio or ratio == float("inf") or ratio == float("-inf"):
        return "?x"
    return f"{ratio:.2f}x"


def compute_table1_rows(*, out_root: Path) -> list[dict[str, str]]:
    """Compute the rows for Table 1 (BLAS idioms where Intuition beats LIAR).

    Returns a list of dicts with keys:
      - kernel
      - liar_solution
      - intuition_solution
      - speedup

    Selection rule:
      Include kernels where the `externs` field differs between baseline and
      foresight in `blas-overview.csv`.

    Speedup rule:
      sp = foresight_speedups['blas.simple.1'] / baseline_speedups['blas.simple.1']
      formatted as 1x.. (clamped).
    """

    base_plots = out_root / "liar" / "baseline" / "plots"
    fore_plots = out_root / "liar" / "foresight" / "plots"

    base_overview = _read_csv_by_key(base_plots / "blas-overview.csv", "name")
    fore_overview = _read_csv_by_key(fore_plots / "blas-overview.csv", "name")

    base_speedups = _read_csv_by_key(base_plots / "speedups.csv", "benchmark")
    fore_speedups = _read_csv_by_key(fore_plots / "speedups.csv", "benchmark")

    rows: list[dict[str, str]] = []

    common_kernels = sorted(set(base_overview.keys()) & set(fore_overview.keys()))
    for k in common_kernels:
        base_externs = (base_overview[k].get("externs") or "").strip()
        fore_externs = (fore_overview[k].get("externs") or "").strip()
        if base_externs == fore_externs:
            continue

        # Speedups are keyed by benchmark name.
        if k not in base_speedups or k not in fore_speedups:
            # Some rows (e.g., geomean) exist only in speedups; ignore missing.
            continue

        base_blas = base_speedups[k].get("blas.simple.1")
        fore_blas = fore_speedups[k].get("blas.simple.1")
        if base_blas is None or fore_blas is None:
            continue

        base_blas_f = _parse_float(base_blas, ctx=f"baseline blas.simple.1 for {k}")
        fore_blas_f = _parse_float(fore_blas, ctx=f"foresight blas.simple.1 for {k}")
        if base_blas_f == 0.0:
            sp = "?x"
        else:
            sp = _format_speedup_x(fore_blas_f / base_blas_f)

        rows.append(
            {
                "kernel": k,
                "liar_solution": base_externs,
                "intuition_solution": fore_externs,
                "speedup": sp,
            }
        )

    return rows
