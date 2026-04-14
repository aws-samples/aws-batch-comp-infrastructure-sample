# Build from satcomp base image
FROM satcomp-infrastructure
USER root

# Install dependencies
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        git gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Clone and build CaDiCaL
ARG CADICAL_VERSION=rel-2.1.3
RUN git clone --depth 1 --branch ${CADICAL_VERSION} https://github.com/arminbiere/cadical.git /cadical
WORKDIR /cadical
RUN ./configure && make -j$(nproc)

# Copy the solver shim from the local directory into the docker image
# The solver shim contains the path to your solver as built above
WORKDIR /
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
