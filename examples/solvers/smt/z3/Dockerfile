FROM satcomp-infrastructure
USER root

# Install build dependencies in a single layer, clean up apt cache
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        apt-utils git cmake gcc g++ m4 python3 \
    && rm -rf /var/lib/apt/lists/*

# Clone and build z3
ARG Z3_VERSION=z3-4.15.4
RUN git clone --depth 1 --branch ${Z3_VERSION} https://github.com/Z3Prover/z3.git /z3

WORKDIR /z3
RUN mkdir build

WORKDIR /z3/build
RUN cmake -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release ../
RUN make -j$(nproc)

WORKDIR /
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
