#!/usr/bin/env python3
"""Experiment module: incremental-eqsat.

All logic specific to the incremental-eqsat experiment lives here.
Imported by scripts/eval.py.

This experiment runs the incremental-eqsat benchmark harness and produces:
  - <out>/incremental-eqsat/measurements.csv
  - <out>/incremental-eqsat/sat-times.csv (cleaned, plotting-friendly)
  - <out>/incremental-eqsat/sat-times.png
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from common import eprint, ensure_dir, run_cmd, write_csv, read_csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# -----------------------------
# incremental-eqsat logic
# -----------------------------


def produce_measurements_csv(*, exp_out: Path) -> Path:
    """Run incremental-eqsat benchmarks and write measurements.csv.

    Returns the path to the generated measurements CSV.
    """

    bench_seconds = os.environ.get("BENCH_SECONDS", "60")

    # The harness expects --size <values...>. We allow TERM_COUNTS to contain
    # either space-separated values ("100 200 300") or a single value.
    term_counts = os.environ.get("TERM_COUNTS", "100 200 300 400 500 600 700 800 900 1000")
    size_args = [x for x in term_counts.split() if x.strip()]

    repo_dir = Path("incremental-eqsat")
    measurements_path = exp_out / "measurements.csv"

    cmd = [
        "python3",
        "-u",
        "run_benchmarks.py",
        "--seconds",
        bench_seconds,
        "--size",
        *size_args,
        "--out",
        str(measurements_path),
    ]

    run_cmd(cmd, cwd=repo_dir, capture_stdout=False)
    eprint(f"[eval] wrote measurements: {measurements_path}")
    return measurements_path


def _find_column(header: Sequence[str], candidates: Sequence[str]) -> Optional[int]:
    idx: Dict[str, int] = {h: i for i, h in enumerate(header)}
    for c in candidates:
        if c in idx:
            return idx[c]
    return None


def _infer_columns(header: Sequence[str]) -> Tuple[int, int, int]:
    """Infer (x, isolated, incremental) column indices from a header.

    This experiment assumes a fixed CSV schema:
      size, incrementalPolynomial, oneByOnePolynomial
    """

    idx: Dict[str, int] = {h: i for i, h in enumerate(header)}

    try:
        x_i = idx["size"]
        incremental_i = idx["incrementalPolynomial"]
        isolated_i = idx["oneByOnePolynomial"]
    except KeyError as e:
        raise KeyError(
            f"expected columns {{'size', 'incrementalPolynomial', 'oneByOnePolynomial'}}, "
            f"got header={list(header)}"
        ) from e

    return x_i, isolated_i, incremental_i


def _parse_float(s: str) -> float:
    # Accept things like "123", "123.4", and "123ms".
    s2 = s.strip()
    if s2.endswith("ms"):
        s2 = s2[:-2].strip()
    return float(s2)


def load_sat_time_series(measurements_path: Path) -> Tuple[List[int], List[float], List[float]]:
    """Load series from measurements.csv.

    Returns: (xs, isolated_ms, incremental_ms) sorted by x.
    """

    header, rows = read_csv(measurements_path)
    x_i, isolated_i, incremental_i = _infer_columns(header)

    triplets: List[Tuple[int, float, float]] = []
    for r in rows:
        if not r:
            continue
        x = int(float(r[x_i]))
        iso = _parse_float(r[isolated_i])
        inc = _parse_float(r[incremental_i])
        triplets.append((x, iso, inc))

    triplets.sort(key=lambda t: t[0])
    xs = [t[0] for t in triplets]
    isolated = [t[1] for t in triplets]
    incremental = [t[2] for t in triplets]
    return xs, isolated, incremental


def write_clean_csv(outdir: Path, xs: Sequence[int], isolated: Sequence[float], incremental: Sequence[float]) -> Path:
    path = outdir / "sat-times.csv"
    header = ["size", "isolated-ms", "incremental-ms"]
    rows: List[List[object]] = []
    for x, iso, inc in zip(xs, isolated, incremental):
        rows.append([x, f"{iso:.9f}".rstrip("0").rstrip("."), f"{inc:.9f}".rstrip("0").rstrip(".")])
    write_csv(path, header, rows)
    eprint(f"[eval] wrote sat-times: {path}")
    return path


def make_line_plot(outdir: Path, xs: Sequence[int], isolated: Sequence[float], incremental: Sequence[float]) -> Path:
    fig, ax = plt.subplots(figsize=(6.2, 2.6))

    ax.plot(xs, isolated, marker="s", linewidth=1.8, label="Isolated")
    ax.plot(xs, incremental, marker="o", linewidth=1.8, label="Incremental")

    ax.set_xlabel("Number of Expressions")
    ax.set_ylabel("Sat. Time (ms)")

    ax.grid(True, which="major", linestyle="-", linewidth=0.6, alpha=0.6)
    ax.legend(loc="upper left")

    fig.tight_layout()
    out_path = outdir / "sat-times.png"
    fig.savefig(out_path, dpi=200)
    plt.close(fig)

    eprint(f"[eval] wrote chart: {out_path}")
    return out_path


def process_measurements_csv(*, exp_out: Path, measurements_path: Path) -> None:
    xs, isolated, incremental = load_sat_time_series(measurements_path)
    write_clean_csv(exp_out, xs, isolated, incremental)
    make_line_plot(exp_out, xs, isolated, incremental)


def run_incremental_eqsat(*, out_root: Path) -> None:
    exp_name = "incremental-eqsat"
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
