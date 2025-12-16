#!/usr/bin/env python3
"""LIAR experiment module.

Outputs (relative to out_root):
  liar/
    baseline/
    foresight/
    plots/
      saturation-speedups.csv
      saturation-speedups.png
      parallelism-speedups-stencil2d.csv
      parallelism-speedups-stencil2d.png
      solution-speedups.csv
      solution-speedups.png
    tables/
      improved-benchmarks.csv

Baseline (cwd = results/liar/baseline):
  python3 liar/src/scripts/liar-evaluation/evaluate_all.py -t300 --limit-steps

Foresight (cwd = results/liar/foresight):
  1) python3 ... --engine=foresight --foresight-thread-counts=1-8 stencil2d --optimize-only --exclude-advanced-strategies
  2) python3 ... --engine=foresight --foresight-thread-counts=1
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil

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
            "--exclude-advanced-strategies",
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
            fieldnames=["kernel", "liar_solution", "foresight_solution", "speedup"],
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

    # -----------------
    # Parallelism speedups (stencil2d components) plot + backing CSV copy.
    par_src = out_root / "liar" / "foresight-parallel" / "plots" / "parallelism-speedups-stencil2d.csv"
    par_csv_path = plots_dir / "parallelism-speedups-stencil2d.csv"
    par_png_path = plots_dir / "parallelism-speedups-stencil2d.png"

    if not par_src.exists():
        raise FileNotFoundError(f"Missing parallelism speedups CSV: {par_src}")

    shutil.copyfile(par_src, par_csv_path)
    write_parallelism_speedups_plot(in_path=par_csv_path, out_path=par_png_path)

    eprint(f"[{EXPERIMENT_NAME}] Copied parallelism speedups CSV to: {par_csv_path}")
    eprint(f"[{EXPERIMENT_NAME}] Wrote parallelism speedups plot to: {par_png_path}")

    # -----------------
    # Figure 9-style runtime speedups across Foresight solutions.
    sol_csv_path = plots_dir / "solution-speedups.csv"
    sol_png_path = plots_dir / "solution-speedups.png"

    sol_rows = compute_solution_speedup_rows(out_root=out_root)

    with sol_csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "kernel",
                "classic_eqsat_speedup",
                "isaria_speedup",
                "sympy_speedup",
            ],
        )
        writer.writeheader()
        writer.writerows(sol_rows)

    write_solution_speedups_bar_chart(rows=sol_rows, out_path=sol_png_path)

    eprint(f"[{EXPERIMENT_NAME}] Wrote solution speedups CSV to: {sol_csv_path}")
    eprint(f"[{EXPERIMENT_NAME}] Wrote solution speedups plot to: {sol_png_path}")


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
    """Compute the rows for Table 1 (BLAS idioms where Foresight beats LIAR).

    Returns a list of dicts with keys:
      - kernel
      - liar_solution
      - foresight_solution
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
                "foresight_solution": fore_externs,
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
        if k not in base or k not in fore or k == 'gemver':
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
        label = f"{sp:.2f}"
        ax.text(i, sp, label, ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def write_parallelism_speedups_plot(*, in_path: Path, out_path: Path) -> None:
    """Plot parallel speedups across components from LIAR's stencil2d run.

    Input CSV schema (columns used):
      - threads
      - total saturation speedup
      - add nodes speedup
      - union speedup
      - metadata for new nodes speedup
      - metadata unification speedup
      - rule application speedup
      - rule matching speedup

    The plot uses a log-scaled y-axis, similar to the paper figure.
    """

    if not in_path.exists():
        raise FileNotFoundError(f"Missing CSV: {in_path}")

    # Read.
    threads: list[int] = []
    series: dict[str, list[float]] = {
        "Total Saturation": [],
        "E-Node Insertions": [],
        "E-Class Unions": [],
        "E-Node Metadata": [],
        "Metadata Unions": [],
        "E-Matching": [],
        "Command Generation": [],
    }

    with in_path.open("r", newline="") as f:
        r = csv.DictReader(f)
        required = [
            "threads",
            "total saturation speedup",
            "add nodes speedup",
            "union speedup",
            "metadata for new nodes speedup",
            "metadata unification speedup",
            "rule application speedup",
            "rule matching speedup",
        ]
        if r.fieldnames is None:
            raise ValueError(f"CSV {in_path} has no header")
        missing = [c for c in required if c not in r.fieldnames]
        if missing:
            raise ValueError(f"CSV {in_path} missing required columns: {missing}")

        for row in r:
            t = int(_parse_float(row["threads"], ctx="threads"))
            threads.append(t)

            series["Total Saturation"].append(
                _parse_float(row["total saturation speedup"], ctx="total saturation speedup")
            )
            series["E-Node Insertions"].append(
                _parse_float(row["add nodes speedup"], ctx="add nodes speedup")
            )
            series["E-Class Unions"].append(
                _parse_float(row["union speedup"], ctx="union speedup")
            )
            series["E-Node Metadata"].append(
                _parse_float(row["metadata for new nodes speedup"], ctx="metadata for new nodes speedup")
            )
            series["Metadata Unions"].append(
                _parse_float(
                    row["metadata unification speedup"],
                    ctx="metadata unification speedup",
                )
            )
            series["Command Generation"].append(
                _parse_float(row["rule application speedup"], ctx="rule application speedup")
            )
            series["E-Matching"].append(
                _parse_float(row["rule matching speedup"], ctx="rule matching speedup")
            )

    if not threads:
        raise ValueError(f"No data rows in CSV: {in_path}")

    # Plot.
    fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=150)

    for label, ys in series.items():
        ax.plot(threads, ys, marker="o", linewidth=1.2, markersize=3, label=label)

    ax.set_xlabel("Number of Threads")
    ax.set_ylabel("Speedup (log scale)")
    ax.set_yscale("log")
    ax.set_xticks(threads)

    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, which="both", linestyle=":", linewidth=0.5)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)

def compute_solution_speedup_rows(*, out_root: Path) -> list[dict[str, str]]:
    """Compute Figure 9-style speedups for multiple Foresight solutions.

    Bars are computed the same way as `compute_table1_rows`, except we also
    pull `blas.isaria.1` and `blas.sympy.1` from the *foresight* speedups CSV.

    All three series are normalized to baseline `blas.simple.1`:
      classic_eqsat = foresight['blas.simple.1'] / baseline['blas.simple.1']
      isaria        = foresight['blas.isaria.1'] / baseline['blas.simple.1']
      sympy         = foresight['blas.sympy.1']  / baseline['blas.simple.1']

    A synthetic `geomean` row is appended (per-series geometric mean).
    """

    base_plots = out_root / "liar" / "baseline" / "plots"
    fore_plots = out_root / "liar" / "foresight" / "plots"

    base_overview = _read_csv_by_key(base_plots / "blas-overview.csv", "name")
    fore_overview = _read_csv_by_key(fore_plots / "blas-overview.csv", "name")

    base_speedups = _read_csv_by_key(base_plots / "speedups.csv", "benchmark")
    fore_speedups = _read_csv_by_key(fore_plots / "speedups.csv", "benchmark")

    # Deterministic kernel order.
    common_kernels = sorted(set(base_overview.keys()) & set(fore_overview.keys()))

    rows: list[dict[str, str]] = []
    classic_vals: list[float] = []
    isaria_vals: list[float] = []
    sympy_vals: list[float] = []

    for k in common_kernels:
        if k not in base_speedups or k not in fore_speedups:
            continue

        base_ref_s = base_speedups[k].get("blas.simple.1")
        if base_ref_s is None:
            continue
        base_ref = _parse_float(base_ref_s, ctx=f"baseline blas.simple.1 for {k}")
        if base_ref <= 0.0:
            continue

        def _maybe_ratio(col: str) -> float | None:
            v = fore_speedups[k].get(col)
            if v is None or (str(v).strip() == ""):
                return None
            fv = _parse_float(v, ctx=f"foresight {col} for {k}")
            return fv / base_ref

        classic = _maybe_ratio("blas.simple.1")
        isaria = _maybe_ratio("blas.isaria.1")
        sympy = _maybe_ratio("blas.sympy.1")

        # If classic is missing, skip the row (can't anchor the plot).
        if classic is None:
            continue

        # Record for geomean (only if present and positive).
        if classic is not None and classic > 0.0:
            classic_vals.append(classic)
        if isaria is not None and isaria > 0.0:
            isaria_vals.append(isaria)
        if sympy is not None and sympy > 0.0:
            sympy_vals.append(sympy)

        rows.append(
            {
                "kernel": k,
                "classic_eqsat_speedup": f"{classic:.6g}",
                "isaria_speedup": "" if isaria is None else f"{isaria:.6g}",
                "sympy_speedup": "" if sympy is None else f"{sympy:.6g}",
            }
        )

    # Append per-series geomean.
    rows.append(
        {
            "kernel": "geomean",
            "classic_eqsat_speedup": f"{_geometric_mean(classic_vals):.6g}",
            "isaria_speedup": f"{_geometric_mean(isaria_vals):.6g}" if isaria_vals else "",
            "sympy_speedup": f"{_geometric_mean(sympy_vals):.6g}" if sympy_vals else "",
        }
    )

    return rows


def write_solution_speedups_bar_chart(*, rows: list[dict[str, str]], out_path: Path) -> None:
    """Write a grouped bar chart for classic/isaria/sympy speedups (Figure 9 style)."""

    # Desired x-axis order (matches paper figure ordering).
    desired_order = [
        "2mm","atax","doitgen","gemm","gesummv","jacobi1d","mvt","1mm","axpy",
        "blur1d","gemv","memset","slim-2mm","stencil2d","vsum","geomean",
    ]

    # Collect rows by kernel first so we can emit in a stable order.
    by_kernel: dict[str, tuple[float, float, float]] = {}

    def _nan_if_missing(v: float | None) -> float:
        return float("nan") if v is None else v

    for r in rows:
        k = (r.get("kernel") or "").strip()
        if not k:
            continue
        c = _f(r.get("classic_eqsat_speedup") or "")
        if c is None:
            continue
        i = _f(r.get("isaria_speedup") or "")
        s = _f(r.get("sympy_speedup") or "")
        by_kernel[k] = (c, _nan_if_missing(i), _nan_if_missing(s))

    kernels: list[str] = []
    classic: list[float] = []
    isaria: list[float] = []
    sympy: list[float] = []

    # Emit in the desired order, skipping any missing kernels.
    for k in desired_order:
        if k not in by_kernel:
            continue
        c, i, s = by_kernel[k]
        kernels.append(k)
        classic.append(c)
        isaria.append(i)
        sympy.append(s)

    # Append any unexpected kernels deterministically, just before geomean if present.
    extras = sorted([k for k in by_kernel.keys() if k not in desired_order])
    if extras:
        insert_at = len(kernels)
        if kernels and kernels[-1] == "geomean":
            insert_at -= 1
        for k in extras:
            c, i, s = by_kernel[k]
            kernels.insert(insert_at, k)
            classic.insert(insert_at, c)
            isaria.insert(insert_at, i)
            sympy.insert(insert_at, s)
            insert_at += 1

    if not kernels:
        raise ValueError("No solution speedup data to plot")

    def _f(s: str) -> float | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
        
    def _span_from_one(vals: list[float]) -> tuple[list[float], list[float]]:
        """Return (bottoms, heights) so each bar spans between 1.0 and v."""
        bottoms: list[float] = []
        heights: list[float] = []
        for v in vals:
            if v != v or v in (float("inf"), float("-inf")) or v <= 0.0:
                bottoms.append(float("nan"))
                heights.append(float("nan"))
                continue
            if v >= 1.0:
                bottoms.append(1.0)
                heights.append(v - 1.0)
            else:
                bottoms.append(v)
                heights.append(1.0 - v)
        return bottoms, heights

    for r in rows:
        k = (r.get("kernel") or "").strip()
        if not k:
            continue
        c = _f(r.get("classic_eqsat_speedup") or "")
        if c is None:
            continue
        kernels.append(k)
        classic.append(c)
        isaria.append(_f(r.get("isaria_speedup") or "") or float("nan"))
        sympy.append(_f(r.get("sympy_speedup") or "") or float("nan"))

    if not kernels:
        raise ValueError("No solution speedup data to plot")

    n = len(kernels)
    x = list(range(n))
    w = 0.22

    fig, ax = plt.subplots(figsize=(10.0, 2.8), dpi=150)

    classic_bottom, classic_h = _span_from_one(classic)
    isaria_bottom, isaria_h = _span_from_one(isaria)
    sympy_bottom, sympy_h = _span_from_one(sympy)

    b1 = ax.bar([xi - w for xi in x], classic_h, bottom=classic_bottom, width=w,
                edgecolor="black", linewidth=0.6, label="Classic EqSat")
    b2 = ax.bar(x, isaria_h, bottom=isaria_bottom, width=w,
                edgecolor="black", linewidth=0.6, label="Isaria")
    b3 = ax.bar([xi + w for xi in x], sympy_h, bottom=sympy_bottom, width=w,
                edgecolor="black", linewidth=0.6, label="SymPy")

    ax.set_yscale("log")
    ax.set_ylabel("Speedup")
    ax.set_xticks(x)
    ax.set_xticklabels(kernels, rotation=45, ha="right")
    ax.axhline(1.0, linewidth=0.8)

    # Clamp around 1.0, matching the paper's plot bounds.
    ax.set_ylim(10 ** (-0.2), 10 ** (0.2))

    def _annotate(bars, vals: list[float]):
        for bar, v in zip(bars, vals):
            if v != v or v in (float("inf"), float("-inf")) or v <= 0.0:
                continue
            xc = bar.get_x() + bar.get_width() / 2.0

            # Bars span between 1 and v. Put the label near the v end.
            if v >= 1.0:
                txt = f"{v:.1f}" if v < 100 else f"{v:.0f}"
                ax.text(xc, v * 1.08, txt, ha="center", va="bottom", fontsize=7)
            else:
                txt = f"{v:.5g}"
                ax.text(xc, v / 1.15, txt, ha="center", va="top", fontsize=7)

    _annotate(b1, classic)
    _annotate(b2, isaria)
    _annotate(b3, sympy)

    ax.legend(loc="upper right", fontsize=8)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.33)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
