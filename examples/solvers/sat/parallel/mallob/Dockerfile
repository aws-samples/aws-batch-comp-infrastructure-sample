FROM satcomp-infrastructure
USER root

#  Install required softwares
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt install -y cmake build-essential zlib1g-dev libopenmpi-dev wget unzip gfortran curl libjemalloc-dev libjemalloc2 gdb

# Build Mallob
RUN git clone https://github.com/domschrei/mallob && cd mallob && git checkout experimental && git checkout 7e96b476d3efd174f9c309fcb75f35bc08ed2984
WORKDIR mallob
RUN cd lib && bash fetch_and_build_solvers.sh klcy
RUN sed -i 's/^new_test.*$//g' CMakeLists.txt src/app/sat/setup.cmake # disable building tests to save time & energy
RUN mkdir build
RUN cd build && cmake -DCMAKE_BUILD_TYPE=RELEASE -DMALLOB_USE_ASAN=0 -DMALLOB_ASSERT=1 -DMALLOB_ASSERT_HEAVY=0 -DMALLOB_USE_JEMALLOC=1 -DMALLOB_JEMALLOC_DIR=/usr/lib/x86_64-linux-gnu -DMALLOB_LOG_VERBOSITY=4 -DMALLOB_SUBPROC_DISPATCH_PATH=\"./\" -DMALLOB_APP_SAT=1 -DMALLOB_APP_SATWITHPRE=1 -DMALLOB_USE_GLUCOSE=0 -DMALLOB_MAX_N_APPTHREADS_PER_PROCESS=64 .. && VERBOSE=1 make -j

# Build ImpCheck
RUN git clone https://github.com/domschrei/impcheck && cd impcheck && git checkout dd07350133506db3b13d16faaf2f80c4f0d0ee1d
RUN cd impcheck && mkdir build && cd build && cmake .. -DCMAKE_BUILD_TYPE=RELEASE -DIMPCHECK_WRITE_DIRECTIVES=0 -DIMPCHECK_FLUSH_ALWAYS=0 && make -j

# TODO maybe uninstall some softwares?
# RUN apt-get update \
#     && DEBIAN_FRONTEND=noninteractive apt install -y libjemalloc-dev libjemalloc2 gdb bc

WORKDIR /

# Copy built binaries to the root of the file system
RUN mv /mallob/build/mallob_sat_process mallob_sat_process \
    && mv /mallob/build/mallob_process_dispatcher mallob_process_dispatcher \
    && mv /mallob/impcheck/build/impcheck_parse impcheck_parse \
    && mv /mallob/impcheck/build/impcheck_check impcheck_check \
    && mv /mallob/impcheck/build/impcheck_confirm impcheck_confirm \
    # We need to move mallob to a temporary location first
    && mv /mallob/build/mallob /mallob_tmp \
    # ...remove the directory
    && rm -rf /mallob \
    # ...then copy mallob into the root of the file system
    && mv /mallob_tmp /mallob

COPY --chown=ecs-user run_solver.sh /
RUN chmod +x /run_solver.sh

COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
