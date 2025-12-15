# Artifact for *Parallel and Customizable Equality Saturation*

This repository contains the evaluation artifact for the CC ’26 paper:

> **Parallel and Customizable Equality Saturation**

The artifact is distributed as a self‑contained Docker image. Running the container executes all experiments and reproduces the tables and figures reported in the paper, writing results to a user‑specified output directory.

---

## Overview

The artifact evaluates **Foresight**, a parallel and customizable equality saturation engine, against several existing systems. It reproduces:

- comparative runtime measurements
- saturation and solution quality speedups
- parallel scalability results
- incremental equality saturation timing results

All experiments are fully automated and require no manual intervention after starting the container.

---

## Quick Start

### 1. Pull the container

```sh
docker pull ghcr.io/jonathanvdc/foresight-cc26-artifact:latest
```

### 2. Run all experiments

From any directory on your machine:

```sh
docker run --rm -it \
  --mount type=bind,src=$PWD/results,dst=/results \
  ghcr.io/jonathanvdc/foresight-cc26-artifact:latest
```

This will:
- run all experiments included in the artifact
- write raw measurements, processed CSVs, and plots into `./results`

---

## Output Structure

After completion, the output directory will contain:

```text
results/
├── foresight-comparison/
│   ├── ratios.csv
│   └── ratios.png
├── incremental-eqsat/
│   ├── sat-times.csv
│   └── sat-times.png
└── liar/
    ├── plots/
    │   ├── saturation-speedups.csv
    │   ├── saturation-speedups.png
    │   ├── parallelism-speedups-stencil2d.csv
    │   ├── parallelism-speedups-stencil2d.png
    │   ├── solution-speedups.csv
    │   └── solution-speedups.png
    └── tables/
        └── improved-benchmarks.csv
```

All CSV files are plain text and suitable for inspection or re‑plotting.

---

## Mapping to Paper Figures and Tables

The artifact outputs correspond directly to the paper as follows:

- **Table 1** → `liar/tables/improved-benchmarks.csv`  
  Benchmarks where Foresight strictly improves over the baseline.

- **Figure 6** → `foresight-comparison/ratios.png`  
  Normalized runtime comparison across equality saturation engines.

- **Figure 7** → `liar/plots/saturation-speedups.png`  
  Speedups from saturation optimizations relative to the LIAR baseline.

- **Figure 8** → `liar/plots/parallelism-speedups-stencil2d.png`  
  Parallel scalability of Foresight on the `stencil2d` benchmark.

- **Figure 9** → `liar/plots/solution-speedups.png`  
  End‑to‑end solution quality speedups.

- **Figure 10** → `incremental-eqsat/sat-times.png`  
  Saturation time comparison for incremental equality saturation.

---

## Experiments

The artifact currently includes the following experiment groups:

- `foresight-comparison`
- `liar`
- `incremental-eqsat`

### Foresight Comparison

This experiment compares Foresight against:
- egg
- hegg
- egglog
- slotted

For each benchmark, the artifact:
1. runs each system
2. records wall‑clock runtimes
3. normalizes runtimes relative to `egg`
4. produces `ratios.csv` and `ratios.png`

### LIAR Benchmarks

These experiments reproduce the LIAR‑based benchmarks used in the paper, producing:
- saturation speedups
- solution quality speedups
- parallel scaling results

### Incremental Equality Saturation

This experiment measures saturation times for incremental equality saturation and produces both raw timing data and summary plots.

---

## Selecting Experiments

By default, **all experiments are run**.

You may run a subset by passing experiment names as positional arguments:

```sh
docker run --rm -it \
  --mount type=bind,src=$PWD/results,dst=/results \
  ghcr.io/jonathanvdc/foresight-cc26-artifact:latest \
  foresight-comparison incremental-eqsat
```

---

## Configuration (Optional)

The container exposes a small number of environment variables for reproducibility and scaling experiments:

| Variable | Default | Description |
|--------|---------|-------------|
| `BENCH_SECONDS` | `60` | Time budget per benchmark (seconds) |
| `FORESIGHT_THREAD_COUNTS` | `"1 8"` | Thread counts used for parallel Foresight |

Example:

```sh
docker run --rm -it \
  --mount type=bind,src=$PWD/results,dst=/results \
  -e BENCH_SECONDS=30 \
  -e FORESIGHT_THREAD_COUNTS="1 4 8" \
  ghcr.io/jonathanvdc/foresight-cc26-artifact:latest
```

---

## Rebuilding the Image (Optional)

Rebuilding the Docker image locally is **not required** for artifact evaluation, but can be done if desired:

```sh
docker build -t foresight-evaluation .
```

and run with:

```sh
docker run --rm -it \
  --mount type=bind,src=$PWD/results,dst=/results \
  foresight-evaluation
```

---

## Notes for Reviewers

- The Docker image is fully self‑contained once pulled.
- No network access is required at runtime.
- All results reported in the paper can be regenerated using the commands above.

---

Thank you for evaluating our artifact!