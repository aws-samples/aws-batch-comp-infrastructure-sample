FROM satcomp-infrastructure
USER root
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get -y upgrade
RUN apt-get install --no-install-recommends -y apt-utils
RUN apt-get install -y git make gcc
#COPY solver_shim_cmd.py /opt/amazon/scripting/harness/solver_shim/solver_shim_cmd.py
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/solver_cmd.py
RUN git clone https://github.com/arminbiere/gimsatul
WORKDIR /gimsatul
RUN git checkout sc2024
# non-quiet mode: easier for debugging
RUN ./configure && make
# RUN ./configure -q && make

WORKDIR /
