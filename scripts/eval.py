

#!/usr/bin/env python3
"""Top-level evaluator for the CC'26 Foresight artifact container.

This script:
- Selects which experiment groups to run (positional args; defaults to all known).
- Writes each experiment's raw measurements into a subdirectory under --outdir.
- Post-processes measurements into derived CSVs and charts.

Currently implemented experiment groups:
- foresight-comparison

Other experiment groups can be added by extending EXPERIMENTS.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


# -----------------------------
# Small helpers
# -----------------------------

def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """Run a command and return stdout as text; raise on failure."""
    eprint(f"[eval] running: {' '.join(cmd)}")
    if cwd is not None:
        eprint(f"[eval]   cwd: {cwd}")
    res = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if res.returncode != 0:
        eprint(res.stdout)
        raise RuntimeError(f"command failed with exit code {res.returncode}: {' '.join(cmd)}")
    return res.stdout


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(header))
        for r in rows:
            w.writerow(list(r))


# -----------------------------
# Experiment: foresight-comparison
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


def parse_measurements_csv_from_stdout(stdout: str) -> Tuple[List[str], List[List[str]]]:
    """Parse the benchmark CSV printed to stdout.

    Expects a header line and data lines like:
      benchmark,slotted,egg,hegg,egglog,foresight_mut_t1,foresight_mut_t8
      mm20,...

    Returns (header, rows) as strings.
    """
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    # Find the first line that looks like the CSV header (starts with 'benchmark,')
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("benchmark,"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("could not find CSV header line starting with 'benchmark,' in stdout")

    csv_lines = lines[header_idx:]

    reader = csv.reader(csv_lines)
    header = next(reader, None)
    if header is None:
        raise ValueError("missing CSV header")

    rows: List[List[str]] = []
    for row in reader:
        if not row:
            continue
        rows.append(row)

    return header, rows


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

    # Map input columns to indices.
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

        # Desired output order:
        # Kernel, egg, egglog, hegg, slotted, foresight, foresight8
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
    # Keep Kernel as-is, and format floats in a stable, spreadsheet-friendly way.
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
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as ex:  # pragma: no cover
        eprint(f"[eval] warning: could not import matplotlib; skipping chart generation: {ex}")
        return

    kernels = [str(r[0]) for r in ratio_rows]
    # columns: egg, egglog, hegg, slotted, foresight, foresight8
    series_names = ["egglog", "hegg", "slotted", "foresight", "foresight8"]
    # indices in our output row
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


def run_foresight_comparison(*, out_root: Path) -> None:
    exp_name = "foresight-comparison"
    exp_out = out_root / exp_name
    ensure_dir(exp_out)

    # Defaults
    bench_seconds = os.environ.get("BENCH_SECONDS", "60")
    foresight_threads = os.environ.get("FORESIGHT_THREAD_COUNTS", "1 8")

    repo_dir = Path("foresight-comparison")

    # Note: thread counts are passed as separate args.
    thread_args = foresight_threads.split()

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
    ]

    stdout = run_cmd(cmd, cwd=repo_dir)

    # Persist the raw stdout for debugging/repro.
    write_text(exp_out / "stdout.txt", stdout)

    header, rows = parse_measurements_csv_from_stdout(stdout)

    # Write raw measurements to measurements.csv
    measurements_path = exp_out / "measurements.csv"
    write_csv(measurements_path, header, rows)
    eprint(f"[eval] wrote measurements: {measurements_path}")

    # Write ratios.csv (normalized by egg)
    ratio_rows = compute_ratios_rows(header, rows)
    ratios_path = exp_out / "ratios.csv"
    write_ratios_csv(ratios_path, ratio_rows)
    eprint(f"[eval] wrote ratios: {ratios_path}")

    # Make charts
    make_ratios_chart(exp_out, ratio_rows)


# -----------------------------
# Registry + CLI
# -----------------------------

@dataclass(frozen=True)
class Experiment:
    name: str
    run: Callable[[Path], None]


EXPERIMENTS: Dict[str, Experiment] = {
    "foresight-comparison": Experiment(
        name="foresight-comparison",
        run=lambda out_root: run_foresight_comparison(out_root=out_root),
    ),
    # Future experiments can be registered here.
    # "liar-reimplementation": Experiment(...),
    # "egglog-extraction": Experiment(...),
}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run CC'26 artifact experiments and post-process results.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "experiments",
        nargs="*",
        help=(
            "Which experiments to run (positional). If omitted, runs all known experiments. "
            f"Known: {', '.join(sorted(EXPERIMENTS.keys()))}"
        ),
    )
    p.add_argument(
        "--outdir",
        default="/results",
        help="Directory to write results into.",
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    out_root = Path(args.outdir)
    ensure_dir(out_root)

    requested: List[str]
    if args.experiments:
        requested = list(args.experiments)
    else:
        requested = sorted(EXPERIMENTS.keys())

    unknown = [x for x in requested if x not in EXPERIMENTS]
    if unknown:
        eprint(
            "[eval] error: unknown experiment(s): "
            + ", ".join(unknown)
            + f". Known: {', '.join(sorted(EXPERIMENTS.keys()))}"
        )
        return 2

    eprint(f"[eval] output directory: {out_root}")
    eprint(f"[eval] experiments to run: {', '.join(requested)}")

    for name in requested:
        eprint(f"[eval] === {name} ===")
        EXPERIMENTS[name].run(out_root)

    eprint("[eval] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))