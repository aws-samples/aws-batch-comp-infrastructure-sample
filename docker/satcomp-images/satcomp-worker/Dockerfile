FROM satcomp-infrastructure:common
RUN apt-get install psmisc
RUN pip3 install flask waitress boto3 pytz polling2
RUN ls 
COPY --chown=ecs-user satcomp-solver-resources/ /opt/amazon/
COPY --chown=ecs-user satcomp-worker/resources/worker /competition/worker
COPY --chown=ecs-user satcomp-worker/resources/cleanup /competition/cleanup
ENV PYTHONPATH=/opt/amazon:.:
RUN chmod u+x /opt/amazon/arg_satcomp_solver_base/worker_entrypoint.py
RUN chmod u+x /competition/worker
RUN chmod u+x /competition/cleanup
RUN service ssh start
USER ecs-user
EXPOSE 22
ENTRYPOINT  /usr/sbin/sshd -D -f /home/ecs-user/.ssh/sshd_config & /opt/amazon/arg_satcomp_solver_base/worker_entrypoint.py