FROM ubuntu:latest

ARG DEBIAN_FRONTEND=noninteractive

# Install base tools, Python, Rust, and Haskell Stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    openssh-client \
    ca-certificates \
    python3 \
    python3-pip \
    python3-psutil \
    pkg-config \
    libssl-dev \
    zlib1g-dev \
    libgmp-dev \
    libtinfo6 \
    haskell-stack \
 && rm -rf /var/lib/apt/lists/*

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Install OpenJDK and sbt (Scala build tool)
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg \
    apt-transport-https \
    ca-certificates \
    curl \
 && mkdir -p /etc/apt/keyrings \
 && curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x99E82A75642AC823" \
    | gpg --dearmor -o /etc/apt/keyrings/sbt-archive-keyring.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/sbt-archive-keyring.gpg] https://repo.scala-sbt.org/scalasbt/debian all main" > /etc/apt/sources.list.d/sbt.list \
 && echo "deb [signed-by=/etc/apt/keyrings/sbt-archive-keyring.gpg] https://scala.jfrog.io/artifactory/debian all main" > /etc/apt/sources.list.d/scala.list \
 && apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jdk \
    sbt \
 && rm -rf /var/lib/apt/lists/*

# (Optional) JAVA_HOME is not strictly required for sbt, but some tools expect it.
# We set it dynamically at shell init time to support multiple architectures.
RUN echo 'export JAVA_HOME="$(dirname $(dirname $(readlink -f $(which javac))))"' > /etc/profile.d/java_home.sh \
 && chmod +x /etc/profile.d/java_home.sh

WORKDIR /workspace

# Install Rust via rustup (ensures latest stable with edition2024 support)
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal \
 && ~/.cargo/bin/rustup update stable \
 && ~/.cargo/bin/rustup default stable \
 && ~/.cargo/bin/rustc --version \
 && ~/.cargo/bin/cargo --version

# Clone and install egglog and egglog-experimental
RUN git clone https://github.com/egraphs-good/egglog-experimental.git /tmp/egglog-experimental \
 && cd /tmp/egglog-experimental \
 # && git checkout 24e3e83016301937f285b2f2ff7889007c5c09b4 \
 && cd / \
 && git clone https://github.com/egraphs-good/egglog.git /tmp/egglog \
 && cd /tmp/egglog \
 # && git checkout b066a521e4710bd74034bfa71a435c26f8ac821f \
 && cd /tmp/egglog-experimental && ~/.cargo/bin/cargo install --path=. \
 && cd /tmp/egglog && ~/.cargo/bin/cargo install --path=. \
 && rm -rf /tmp/egglog /tmp/egglog-experimental

# Install GHC via ghcup and use it with Stack (to avoid stack downloading/compiling GHC)
# This image builds/runs as root by default, so install into /root for determinism.
ENV GHCUP_INSTALL_BASE_PREFIX="/root"
RUN curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org \
    | BOOTSTRAP_HASKELL_NONINTERACTIVE=1 BOOTSTRAP_HASKELL_MINIMAL=1 sh \
 && /root/.ghcup/bin/ghcup --version \
 # Install a GHC for hegg-bench
 && /root/.ghcup/bin/ghcup install ghc 9.6.6 \
 && /root/.ghcup/bin/ghcup set ghc 9.6.6

# Put ghcup/GHC/cabal and cargo on PATH
ENV PATH="/root/.ghcup/bin:/root/.cabal/bin:/root/.cargo/bin:${PATH}"

# Set Stack’s working directory
ENV STACK_ROOT="/root/.stack"

COPY . /workspace

# Clone benchmark repositories
RUN git clone --recursive https://github.com/jonathanvdc/foresight-comparison.git /workspace/foresight-comparison

# (Optional) Pre-build benchmark projects
RUN cd /workspace/foresight-comparison/slotted && cargo build --release
RUN cd /workspace/foresight-comparison/egg && cargo build --release
RUN cd /workspace/foresight-comparison/hegg-bench && stack --system-ghc --no-install-ghc build
RUN cd /workspace/foresight-comparison/foresight && sbt benchmarks/jmh:compile

# # Default command: run benchmarks with --seconds from env variable, redirecting all output to stderr
# CMD ["/bin/bash", "-lc", "python3 -u run_benchmarks.py --seconds \"${BENCH_SECONDS}\" --foresight-thread-counts ${FORESIGHT_THREAD_COUNTS} --foresight-mutable-egraph true 1>&2 && cat results.csv"]