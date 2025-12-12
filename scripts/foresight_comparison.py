#!/usr/bin/env python3
"""Experiment module: foresight-comparison.

All logic specific to the foresight-comparison experiment lives here.
Imported by scripts/eval.py.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from common import eprint, ensure_dir, run_cmd, write_csv, read_csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# -----------------------------
# foresight-comparison logic
# -----------------------------

INPUT_HEADER = [
    "benchmark",
    "slotted",
    "egg",
    "hegg",
    "egglog",
    "foresight_mut_t1",
    "foresight_mut_t8",
]

OUTPUT_HEADER = ["Kernel", "egg", "egglog", "hegg", "slotted", "foresight", "foresight8"]


def produce_measurements_csv(*, exp_out: Path) -> Path:
    """Run foresight-comparison benchmarks and write measurements.csv.

    Returns the path to the generated measurements CSV.
    """
    bench_seconds = os.environ.get("BENCH_SECONDS", "60")
    foresight_threads = os.environ.get("FORESIGHT_THREAD_COUNTS", "1 8")

    repo_dir = Path("foresight-comparison")
    thread_args = foresight_threads.split()

    measurements_path = exp_out / "measurements.csv"

    cmd = [
        "python3",
        "-u",
        "run_benchmarks.py",
        "--seconds",
        bench_seconds,
        "--foresight-thread-counts",
        *thread_args,
        "--foresight-mutable-egraph",
        "true",
        "--out",
        str(measurements_path),
    ]

    run_cmd(cmd, cwd=repo_dir, capture_stdout=False)
    eprint(f"[eval] wrote measurements: {measurements_path}")

    return measurements_path


def normalize_kernel_name(raw: str) -> Optional[str]:
    """Rename benchmarks.

    - mm20 -> 20mm (and similarly mm40 -> 40mm, etc.)
    - poly5 -> Horner
    - poly6 is dropped
    - Everything else is left unchanged.
    """
    if raw == "poly6":
        return None
    if raw == "poly5":
        return "Horner"
    m = re.fullmatch(r"mm(\d+)", raw)
    if m:
        return f"{m.group(1)}mm"
    return raw


def compute_ratios_rows(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> List[List[object]]:
    """Convert raw measurements into ratio rows divided by egg."""

    idx: Dict[str, int] = {name: i for i, name in enumerate(header)}
    missing = [c for c in INPUT_HEADER if c not in idx]
    if missing:
        raise ValueError(f"missing expected columns in measurements: {missing}; got header={list(header)}")

    out_rows: List[List[object]] = []
    for r in rows:
        bench = r[idx["benchmark"]]
        kernel = normalize_kernel_name(bench)
        if kernel is None:
            continue

        def f(col: str) -> float:
            return float(r[idx[col]])

        egg = f("egg")
        if egg == 0.0:
            raise ValueError(f"egg runtime is 0 for benchmark {bench}, cannot divide")

        out_rows.append(
            [
                kernel,
                1.0,  # egg/egg
                f("egglog") / egg,
                f("hegg") / egg,
                f("slotted") / egg,
                f("foresight_mut_t1") / egg,
                f("foresight_mut_t8") / egg,
            ]
        )

    return out_rows


def format_ratio_cell(x: object) -> object:
    if isinstance(x, float):
        return f"{x:.9f}".rstrip("0").rstrip(".")
    return x


def write_ratios_csv(path: Path, ratio_rows: Sequence[Sequence[object]]) -> None:
    formatted = [[format_ratio_cell(x) for x in row] for row in ratio_rows]
    write_csv(path, OUTPUT_HEADER, formatted)


def make_ratios_chart(outdir: Path, ratio_rows: Sequence[Sequence[object]]) -> None:
    """Generate a simple grouped-bar chart from ratios.csv.

    Produces: <outdir>/ratios.png
    """
    kernels = [str(r[0]) for r in ratio_rows]
    series_names = ["egglog", "hegg", "slotted", "foresight", "foresight8"]
    series_idx = [2, 3, 4, 5, 6]

    values: List[List[float]] = []
    for si in series_idx:
        values.append([float(r[si]) for r in ratio_rows])

    import numpy as np

    x = np.arange(len(kernels))
    width = 0.14

    fig, ax = plt.subplots(figsize=(max(7.0, 1.4 * len(kernels)), 4.2))
    for i, (name, vals) in enumerate(zip(series_names, values)):
        ax.bar(x + (i - (len(series_names) - 1) / 2) * width, vals, width, label=name)

    ax.set_xticks(x)
    ax.set_xticklabels(kernels)
    ax.set_ylabel("Runtime relative to egg (lower is better)")
    ax.set_title("Foresight comparison (ratios)")
    ax.axhline(1.0, linewidth=1)
    ax.legend(ncol=min(3, len(series_names)), fontsize=9)
    fig.tight_layout()

    out_path = outdir / "ratios.png"
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    eprint(f"[eval] wrote chart: {out_path}")


def process_measurements_csv(*, exp_out: Path, measurements_path: Path) -> None:
    """Process an existing measurements.csv into ratios.csv and ratios.png."""
    header, rows = read_csv(measurements_path)

    ratio_rows = compute_ratios_rows(header, rows)
    ratios_path = exp_out / "ratios.csv"
    write_ratios_csv(ratios_path, ratio_rows)
    eprint(f"[eval] wrote ratios: {ratios_path}")

    make_ratios_chart(exp_out, ratio_rows)


def run_foresight_comparison(*, out_root: Path) -> None:
    exp_name = "foresight-comparison"
    exp_out = out_root / exp_name
    ensure_dir(exp_out)

    measurements_path = exp_out / "measurements.csv"

    # By default, do not regenerate measurements if they already exist.
    # Set FORCE_RERUN=1 to rerun benchmarks and overwrite measurements.csv.
    force_rerun = os.environ.get("FORCE_RERUN", "0") not in ("0", "false", "False", "")

    if (not force_rerun) and measurements_path.exists():
        eprint(f"[eval] reusing existing measurements: {measurements_path}")
    else:
        measurements_path = produce_measurements_csv(exp_out=exp_out)

    process_measurements_csv(exp_out=exp_out, measurements_path=measurements_path)
