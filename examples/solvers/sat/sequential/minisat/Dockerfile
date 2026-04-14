FROM satcomp-infrastructure
USER root

# Install build dependencies
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        gcc g++ make zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and extract MiniSat 2.2.0 tarball
COPY minisat-2.2.0.tar.gz /tmp/
RUN tar xzf /tmp/minisat-2.2.0.tar.gz -C / && rm /tmp/minisat-2.2.0.tar.gz

# Build MiniSat
# MiniSat 2.2.0 requires patches for modern compilers (GCC 13+):
# 1. Missing includes in System.cc
# 2. -fpermissive for friend declaration default args and other C++11 issues
# 3. Suppress -Wclass-memaccess warnings from vec realloc usage
WORKDIR /minisat
RUN sed -i '1i #include <cstdlib>' utils/System.cc \
    && sed -i '1i #include <climits>' utils/System.cc \
    && echo 'CFLAGS += -fpermissive -Wno-class-memaccess' >> mtl/config.mk \
    && export MROOT=$(pwd) && cd simp && make rs -j$(nproc)

WORKDIR /
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
