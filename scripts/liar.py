#!/usr/bin/env python3
"""LIAR experiment module.

Outputs (relative to out_root):
  liar/
    baseline/
    foresight/
    plots/
      saturation-speedups.csv
      saturation-speedups.png

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
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


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

    # -----------------
    # Table 1 (paper).
    tables_dir = liar_dir / "tables"
    ensure_dir(tables_dir)
    table1_path = tables_dir / "improved-benchmarks.csv"
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

    eprint(f"[{EXPERIMENT_NAME}] Wrote improved benchmarks to: {table1_path}")

    # -----------------
    # Saturation speedups bar chart + backing CSV.
    plots_dir = liar_dir / "plots"
    ensure_dir(plots_dir)

    sat_csv_path = plots_dir / "saturation-speedups.csv"
    sat_png_path = plots_dir / "saturation-speedups.png"

    sat_rows = compute_saturation_speedup_rows(out_root=out_root)

    with sat_csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["kernel", "baseline_time_s", "foresight_time_s", "speedup"],
        )
        writer.writeheader()
        writer.writerows(sat_rows)

    write_saturation_speedups_bar_chart(rows=sat_rows, out_path=sat_png_path)

    eprint(f"[{EXPERIMENT_NAME}] Wrote saturation speedups CSV to: {sat_csv_path}")
    eprint(f"[{EXPERIMENT_NAME}] Wrote saturation speedups bar chart to: {sat_png_path}")


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


def compute_saturation_speedup_rows(*, out_root: Path) -> list[dict[str, str]]:
    """Compute saturation speedups from BLAS overview CSVs.

    Speedup is computed as:
        speedup = baseline_time / foresight_time

    using the `time` column from:
      - out_root/liar/baseline/plots/blas-overview.csv
      - out_root/liar/foresight/plots/blas-overview.csv

    The returned list is in a deterministic order matching the order of kernels
    found in the baseline CSV (excluding any existing "geomean" row). A
    synthetic "geomean" row is appended.

    Output row schema:
      - kernel
      - baseline_time_s
      - foresight_time_s
      - speedup
    """

    base_path = out_root / "liar" / "baseline" / "plots" / "blas-overview.csv"
    fore_path = out_root / "liar" / "foresight" / "plots" / "blas-overview.csv"

    # Preserve baseline CSV order for the chart.
    baseline_order: list[str] = []
    with base_path.open("r", newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames is None or "name" not in r.fieldnames or "time" not in r.fieldnames:
            raise ValueError(f"CSV {base_path} missing required columns: name,time")
        for row in r:
            k = (row.get("name") or "").strip()
            if not k or k == "geomean":
                continue
            baseline_order.append(k)

    base = _read_csv_by_key(base_path, "name")
    fore = _read_csv_by_key(fore_path, "name")

    speedups: list[tuple[str, float, float, float]] = []

    for k in baseline_order:
        if k not in base or k not in fore:
            continue
        bt_s = base[k].get("time")
        ft_s = fore[k].get("time")
        if bt_s is None or ft_s is None:
            continue

        bt = _parse_float(bt_s, ctx=f"baseline time for {k}")
        ft = _parse_float(ft_s, ctx=f"foresight time for {k}")
        if ft <= 0.0:
            continue

        sp = bt / ft
        speedups.append((k, bt, ft, sp))

    # Geometric mean of speedups.
    geomean = _geometric_mean([sp for (_, _, _, sp) in speedups])

    out_rows: list[dict[str, str]] = []
    for (k, bt, ft, sp) in speedups:
        out_rows.append(
            {
                "kernel": k,
                "baseline_time_s": f"{bt:.6f}",
                "foresight_time_s": f"{ft:.6f}",
                "speedup": f"{sp:.2f}",
            }
        )

    out_rows.append(
        {
            "kernel": "geomean",
            "baseline_time_s": "",
            "foresight_time_s": "",
            "speedup": f"{geomean:.2f}",
        }
    )

    return out_rows


def _geometric_mean(values: list[float]) -> float:
    if not values:
        return float("nan")
    # Clamp to avoid log(0) / negative; speedups should be positive.
    logs: list[float] = []
    for v in values:
        if v <= 0.0 or v != v or v == float("inf") or v == float("-inf"):
            continue
        logs.append(math.log(v))
    if not logs:
        return float("nan")
    return math.exp(sum(logs) / len(logs))


def write_saturation_speedups_bar_chart(*, rows: list[dict[str, str]], out_path: Path) -> None:
    """Write a bar chart similar to the paper figure.

    Expects `rows` in the same schema as produced by
    `compute_saturation_speedup_rows`.
    """

    kernels: list[str] = []
    speedups: list[float] = []

    for r in rows:
        k = (r.get("kernel") or "").strip()
        s = (r.get("speedup") or "").strip()
        if not k or not s:
            continue
        try:
            sp = float(s)
        except ValueError:
            continue
        kernels.append(k)
        speedups.append(sp)

    if not kernels:
        raise ValueError("No saturation speedup data to plot")

    # Plot.
    fig, ax = plt.subplots(figsize=(6.4, 3.2), dpi=150)
    ax.bar(range(len(kernels)), speedups, edgecolor="black", linewidth=0.7)

    ax.set_yscale("log")
    ax.set_ylabel("Speedup")
    ax.set_xlabel("Kernel")

    ax.set_xticks(range(len(kernels)))
    ax.set_xticklabels(kernels, rotation=45, ha="right")

    # Annotate values on top of bars.
    for i, sp in enumerate(speedups):
        label = f"{sp:.0f}" if sp >= 10.0 else f"{sp:.2f}"
        ax.text(i, sp, label, ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
