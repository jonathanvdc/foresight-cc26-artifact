# Artifact for *Parallel and Customizable Equality Saturation*

This repository contains the evaluation artifact for the CC '26 paper:

> **Parallel and Customizable Equality Saturation**

The artifact is packaged as a **self-contained Docker image** that runs all experiments and produces the figures and tables reported in the paper.

---

## Quick Start

To evaluate the artifact, the Docker container and run it directly.

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

After completion, you should see:

```text
results/
└── foresight-comparison/
    ├── measurements.csv
    ├── ratios.csv
    ├── ratios.png
    └── stdout.txt
```

The total runtime is on the order of a few minutes on a typical modern machine.

---

## What the Artifact Does

The artifact evaluates **Foresight**, a parallel and customizable equality saturation engine, against several existing systems. The experiments reproduce the performance comparison discussed in the paper.

Currently included experiment groups:

- `foresight-comparison`

### `foresight-comparison`

This experiment group compares Foresight against:
  - egg
  - hegg
  - egglog
  - slotted

For each benchmark kernel, the artifact:
1. runs each system
2. records wall-clock runtimes
3. normalizes all runtimes relative to `egg`
4. generates a CSV (`ratios.csv`) and a bar chart (`ratios.png`)

---

## Selecting Experiments

By default, all available experiments are run.
You may optionally select a subset by passing positional arguments to the container.

For example, to run only the Foresight comparison:

```sh
docker run --rm -it \
  --mount type=bind,src=$PWD/results,dst=/results \
  ghcr.io/jonathanvdc/foresight-cc26-artifact:latest \
  foresight-comparison
```

---

## Configuration (Optional)

The container exposes a small number of environment variables for reproducibility experiments:

| Variable | Default | Meaning |
|--------|---------|---------|
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

## Output Files

Each experiment writes its results to a subdirectory of `/results`:

- `measurements.csv` – raw benchmark timings
- `ratios.csv` – timings normalized to `egg`
- `ratios.png` – bar chart used for visual comparison
- `stdout.txt` – full captured stdout of the experiment script (for debugging/reproducibility)

All CSV files are plain-text and suitable for inspection or re-plotting.

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

- Once built, the Docker image is fully self-contained.
- The container does not require network access at runtime.

---

Thank you for evaluating our artifact!