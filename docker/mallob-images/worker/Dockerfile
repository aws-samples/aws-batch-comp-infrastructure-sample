################### Use Mallob
FROM satcomp-mallob:common AS builder
USER root

################### Extract Mallob in run stage
FROM satcomp-infrastructure:worker AS mallob_liaison
WORKDIR /
# Copy mallob
COPY --from=builder /mallob/build/mallob mallob
COPY --from=builder /mallob/build/mallob_sat_process mallob_sat_process
COPY --chown=ecs-user /worker /competition

RUN chmod +x /competition/worker
