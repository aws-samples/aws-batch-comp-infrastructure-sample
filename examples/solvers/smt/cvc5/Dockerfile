FROM satcomp-infrastructure
USER root

# Install build dependencies in a single layer, clean up apt cache
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        apt-utils git cmake gcc g++ m4 python3 \
    && rm -rf /var/lib/apt/lists/*

# Clone and build cvc5
ARG CVC5_VERSION=cvc5-1.3.2
RUN git clone --depth 1 --branch ${CVC5_VERSION} https://github.com/cvc5/cvc5.git /cvc5

WORKDIR /cvc5
RUN ./configure.sh --auto-download

WORKDIR /cvc5/build
RUN make -j$(nproc)
RUN make -j$(nproc) check

WORKDIR /
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
