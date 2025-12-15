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

BASE_INPUT_HEADER = [
    "benchmark",
    "slotted",
    "egg",
    "hegg",
    "egglog",
]

BASE_OUTPUT_HEADER = ["Kernel", "egg", "egglog", "hegg", "slotted"]


def parse_thread_counts(s: str) -> List[int]:
    # Accept whitespace-separated integers. Preserve order of first occurrence.
    out: List[int] = []
    seen: set[int] = set()
    for tok in s.split():
        tok = tok.strip()
        if not tok:
            continue
        t = int(tok)
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def foresight_col_for_thread(t: int) -> str:
    return f"foresight_mut_t{t}"


def threads_in_measurements_header(header: Sequence[str]) -> List[int]:
    """Extract available Foresight thread counts from a measurements.csv header."""
    threads: List[int] = []
    for h in header:
        m = re.fullmatch(r"foresight_mut_t(\d+)", h)
        if m:
            threads.append(int(m.group(1)))
    threads.sort()
    return threads


def produce_measurements_csv(*, exp_out: Path) -> Path:
    """Run foresight-comparison benchmarks and write measurements.csv.

    Returns the path to the generated measurements CSV.
    """
    bench_seconds = os.environ.get("BENCH_SECONDS", "60")
    jmh_jvm_ram = os.environ.get("JMH_JVM_RAM", "16g")
    foresight_threads = os.environ.get("FORESIGHT_THREAD_COUNTS", "1 8")

    repo_dir = Path("foresight-comparison")
    thread_args = [str(t) for t in parse_thread_counts(foresight_threads)]

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
        f"--jmh-jvm-opts=-Xmx{jmh_jvm_ram}",
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
    *,
    foresight_threads: Sequence[int],
) -> Tuple[List[str], List[List[object]]]:
    idx: Dict[str, int] = {name: i for i, name in enumerate(header)}

    missing_base = [c for c in BASE_INPUT_HEADER if c not in idx]
    if missing_base:
        raise ValueError(f"missing expected base columns in measurements: {missing_base}; got header={list(header)}")

    foresight_cols: List[str] = [foresight_col_for_thread(t) for t in foresight_threads]
    missing_foresight = [c for c in foresight_cols if c not in idx]
    if missing_foresight:
        raise ValueError(
            f"missing expected foresight thread columns in measurements: {missing_foresight}; got header={list(header)}"
        )

    out_header = BASE_OUTPUT_HEADER + [f"foresight_t{t}" for t in foresight_threads]

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

        row_out: List[object] = [
            kernel,
            1.0,  # egg/egg
            f("egglog") / egg,
            f("hegg") / egg,
            f("slotted") / egg,
        ]

        for c in foresight_cols:
            row_out.append(f(c) / egg)

        out_rows.append(row_out)

    return out_header, out_rows


def format_ratio_cell(x: object) -> object:
    if isinstance(x, float):
        return f"{x:.9f}".rstrip("0").rstrip(".")
    return x


def write_ratios_csv(path: Path, header: Sequence[str], ratio_rows: Sequence[Sequence[object]]) -> None:
    formatted = [[format_ratio_cell(x) for x in row] for row in ratio_rows]
    write_csv(path, list(header), formatted)


def make_ratios_chart(outdir: Path, header: Sequence[str], ratio_rows: Sequence[Sequence[object]]) -> None:
    """Generate a simple grouped-bar chart from ratios.csv.

    Produces: <outdir>/ratios.png
    """
    kernels = [str(r[0]) for r in ratio_rows]

    # Base series (omit egg because it's always 1.0)
    base_series = [
        ("egglog", 2),
        ("hegg", 3),
        ("slotted", 4),
    ]

    # Foresight series are any columns in the output header that start with "foresight_t".
    foresight_cols: List[Tuple[str, int]] = []
    for i, name in enumerate(header):
        if name.startswith("foresight_t"):
            foresight_cols.append((name, i))

    # Nicer legend names:
    # - If exactly {1, X}, call them Sequential/Parallel.
    # - Otherwise: Sequential for t=1, and "Foresight (<t> threads)" for others.
    fs_threads: List[int] = []
    for name, _ in foresight_cols:
        m = re.fullmatch(r"foresight_t(\d+)", name)
        if m:
            fs_threads.append(int(m.group(1)))
    fs_threads_sorted = sorted(fs_threads)
    two_way = (len(fs_threads_sorted) == 2 and 1 in fs_threads_sorted)
    parallel_t = max(fs_threads_sorted) if fs_threads_sorted else None

    series: List[Tuple[str, int]] = []
    series.extend(base_series)
    for name, idx_col in foresight_cols:
        m = re.fullmatch(r"foresight_t(\d+)", name)
        t = int(m.group(1)) if m else None
        if t == 1:
            label = "Foresight (Sequential)"
        elif two_way and t == parallel_t:
            label = "Foresight (Parallel)"
        elif t is not None:
            label = f"Foresight ({t} threads)"
        else:
            label = name
        series.append((label, idx_col))

    series_names = [n for (n, _) in series]
    series_idx = [i for (_, i) in series]

    import numpy as np

    x = np.arange(len(kernels))
    width = 0.14

    fig, ax = plt.subplots(figsize=(max(7.0, 1.4 * len(kernels)), 4.2))
    for i, (name, vals) in enumerate(zip(series_names, [[float(r[j]) for r in ratio_rows] for j in series_idx])):
        ax.bar(x + (i - (len(series_names) - 1) / 2) * width, vals, width, label=name)

    ax.set_xticks(x)
    ax.set_xticklabels(kernels)
    ax.set_ylabel("Runtime relative to egg (lower is better)")
    ax.set_yscale("log")
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

    # Determine which thread counts are available in the file.
    fs_threads_in_file = threads_in_measurements_header(header)

    out_header, ratio_rows = compute_ratios_rows(header, rows, foresight_threads=fs_threads_in_file)
    ratios_path = exp_out / "ratios.csv"
    write_ratios_csv(ratios_path, out_header, ratio_rows)
    eprint(f"[eval] wrote ratios: {ratios_path}")

    make_ratios_chart(exp_out, out_header, ratio_rows)


def run_foresight_comparison(*, out_root: Path) -> None:
    exp_name = "foresight-comparison"
    exp_out = out_root / exp_name
    ensure_dir(exp_out)

    measurements_path = exp_out / "measurements.csv"

    # By default, do not regenerate measurements if they already exist.
    # Set FORCE_RERUN=1 to rerun benchmarks and overwrite measurements.csv.
    force_rerun = os.environ.get("FORCE_RERUN", "0") not in ("0", "false", "False", "")

    if (not force_rerun) and measurements_path.exists():
        file_header, _ = read_csv(measurements_path)
        existing_threads = set(threads_in_measurements_header(file_header))

        requested_threads = set(parse_thread_counts(os.environ.get("FORESIGHT_THREAD_COUNTS", "1 8")))

        if existing_threads.issubset(requested_threads):
            eprint(f"[eval] reusing existing measurements: {measurements_path}")
        else:
            eprint(
                "[eval] existing measurements thread counts do not match requested; "
                f"existing={sorted(existing_threads)} requested={sorted(requested_threads)}; rerunning"
            )
            measurements_path = produce_measurements_csv(exp_out=exp_out)
    else:
        measurements_path = produce_measurements_csv(exp_out=exp_out)

    process_measurements_csv(exp_out=exp_out, measurements_path=measurements_path)
