

#!/usr/bin/env python3
"""Shared helper utilities for artifact evaluation scripts."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def eprint(*args: object) -> None:
    """Print to stderr."""
    print(*args, file=sys.stderr)


def ensure_dir(p: Path) -> None:
    """Create directory p (including parents) if it does not exist."""
    p.mkdir(parents=True, exist_ok=True)


def run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    capture_stdout: bool = True,
) -> Optional[str]:
    """Run a command; optionally capture stdout; raise on failure.

    If capture_stdout=True (default), stdout is captured and returned as text.
    If capture_stdout=False, stdout is inherited from the parent process and
    None is returned. In all cases, stderr is inherited.
    """
    eprint(f"[eval] running: {' '.join(cmd)}")
    if cwd is not None:
        eprint(f"[eval]   cwd: {cwd}")

    res = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE if capture_stdout else None,
        stderr=None,  # inherit: forward stderr to parent process
        check=False,
    )

    if res.returncode != 0:
        if capture_stdout and res.stdout:
            eprint(res.stdout)
        raise RuntimeError(
            f"command failed with exit code {res.returncode}: {' '.join(cmd)}"
        )

    if capture_stdout:
        return res.stdout
    return None

def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(header))
        for r in rows:
            w.writerow(list(r))

def read_csv(path: Path) -> Tuple[List[str], List[List[str]]]:
    """Read a CSV file and return (header, rows) as strings."""
    with path.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"missing CSV header in {path}")
        rows: List[List[str]] = [row for row in reader if row]
    return header, rows
