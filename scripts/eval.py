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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Sequence
from common import eprint, ensure_dir, run_cmd


# -----------------------------
# Experiment modules
# -----------------------------
from foresight_comparison import run_foresight_comparison


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
        run=lambda out_root: (
            run_foresight_comparison(out_root=out_root)
        ),
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
