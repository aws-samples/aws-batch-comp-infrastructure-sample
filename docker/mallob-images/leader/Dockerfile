################### Use Mallob
FROM satcomp-mallob:common AS builder
USER root


################### Extract Mallob in run stage
FROM satcomp-infrastructure:leader AS mallob_liaison
WORKDIR /
# Copy mallob and solver scripts
COPY --from=builder /mallob/build/mallob mallob
COPY --from=builder /mallob/build/mallob_sat_process mallob_sat_process
COPY --from=builder /mallob/build/mallob_process_dispatcher mallob_process_dispatcher

COPY --chown=ecs-user /init_solver.sh /competition
COPY --chown=ecs-user /run_solver.sh /competition
COPY --chown=ecs-user /solver /competition
USER ecs-user
RUN chmod +x /competition/init_solver.sh
RUN chmod +x /competition/run_solver.sh
RUN chmod +x /competition/solver