FROM satcomp-infrastructure
USER root

ENV DEBIAN_FRONTEND noninteractive

# Install required software
RUN apt-get update \
    && apt install -y apt-utils make cmake \
       build-essential libgmp-dev bison flex git python3-dev nano bc wget zstd \
    && rm -rf /var/lib/apt/lists/*

ENV CMAKE_BUILD_TYPE Release
ENV ENABLE_LINE_EDITING OFF
ENV PARALLEL ON

# Fetch and build SMTS
RUN git clone https://github.com/usi-verification-and-security/SMTS.git --branch smtcomp26-aws --single-branch --depth 1 /SMTS

WORKDIR /SMTS
RUN \
    export CMAKE_BUILD_PARALLEL_LEVEL=$(nproc) && \
    sh bin/make_smts.sh && \
    rm -rf \
        graphviz \
        gui \
        build/lib \
        build/_deps/ptplib-src/tests \
        build/_deps/opensmt-src/regression* \
        build/_deps/opensmt-src/benchmark \
        build/_deps/opensmt-src/docs \
        build/_deps/opensmt-src/examples

WORKDIR /
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
