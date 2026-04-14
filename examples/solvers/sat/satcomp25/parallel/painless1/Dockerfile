################### Build Painless
FROM satcomp-infrastructure
USER root

#  Install required softwares (Boost needed for Painless)

# Install required packages
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y vim cmake build-essential zlib1g-dev libopenmpi-dev wget unzip python3 gfortran curl

# g++-10 for better c++20 support
RUN apt-get --install-recommends install -y libboost-all-dev g++-10 protobuf-compiler
RUN ln -sf /usr/bin/g++-10 /usr/bin/g++
#--branch satcomp-25
RUN git clone https://github.com/lip6/painless.git --branch v1.25-isc25

# Build Painless
WORKDIR /painless
RUN make -j $(nproc)

#####

WORKDIR /

COPY --chown=ecs-user run_solver.sh /
RUN chmod +x /run_solver.sh

RUN cp /painless/painless /painless-solver
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/

#####

# RUN apt-get update && apt-get --install-recommends install -y libboost-all-dev protobuf-compiler

# COPY --chown=ecs-user leader/init_solver.sh /competition/init_solver.sh
# COPY --chown=ecs-user leader/run_solver.sh /competition/run_solver.sh

# USER ecs-user
# RUN chmod +x /competition/init_solver.sh
# RUN chmod +x /competition/run_solver.sh
