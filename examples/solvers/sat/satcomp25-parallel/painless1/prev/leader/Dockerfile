FROM painless1:common AS builder
USER root

FROM satcomp-infrastructure:leader AS mallob_liaison

WORKDIR /

COPY solver_shim_cmd.py /opt/amazon/scripting/harness/solver_shim/solver_shim_cmd.py

COPY --from=builder /painless/painless painless

USER root

# Needed sharer libraries
RUN apt-get update && apt-get --install-recommends install -y libboost-all-dev protobuf-compiler

COPY --chown=ecs-user leader/init_solver.sh /competition/init_solver.sh
COPY --chown=ecs-user leader/run_solver.sh /competition/run_solver.sh

USER ecs-user
RUN chmod +x /competition/init_solver.sh
RUN chmod +x /competition/run_solver.sh
