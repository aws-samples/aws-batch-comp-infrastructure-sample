FROM satcomp-infrastructure
USER root

# Install build dependencies
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        git gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Clone and build Kissat
ARG KISSAT_VERSION=rel-4.0.1
RUN git clone --depth 1 --branch ${KISSAT_VERSION} https://github.com/arminbiere/kissat.git /kissat

WORKDIR /kissat
RUN ./configure && make -j$(nproc)

WORKDIR /
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
