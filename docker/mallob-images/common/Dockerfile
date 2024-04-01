################### Build Mallob
FROM satcomp-infrastructure:common
USER root
#  Install required softwares
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt install -y cmake build-essential zlib1g-dev libopenmpi-dev wget unzip build-essential zlib1g-dev cmake python3 build-essential gfortran wget curl

# Build Mallob
RUN git clone https://github.com/domschrei/mallob && cd mallob && git checkout interface && git checkout 35794bfa9d650f7c465c08cd0073a71833119162 && cd ..
WORKDIR mallob
RUN cd lib && bash fetch_and_build_sat_solvers.sh klcy && cd ..
RUN mkdir build
RUN cd build && cmake -DCMAKE_BUILD_TYPE=RELEASE -DMALLOB_USE_RESTRICTED=1 .. && VERBOSE=1 make && cd ..
