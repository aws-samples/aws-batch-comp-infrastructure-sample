FROM satcomp-infrastructure:common
RUN pip3 install flask waitress boto3 pytz polling2
COPY --chown=ecs-user satcomp-solver-resources /opt/amazon/arg_satcomp_solver_base
COPY --chown=ecs-user satcomp-leader/resources/solver /competition/solver
COPY --chown=ecs-user satcomp-leader/resources/leader /competition/leader
ENV PYTHONPATH=/opt/amazon:.:
RUN chmod u+x /competition/solver
RUN chmod u+x /competition/leader
RUN chmod u+x /opt/amazon/arg_satcomp_solver_base/leader_entrypoint.py
RUN service ssh start
USER ecs-user
EXPOSE 22
ENTRYPOINT  /usr/sbin/sshd -D -f /home/ecs-user/.ssh/sshd_config & /opt/amazon/arg_satcomp_solver_base/leader_entrypoint.py