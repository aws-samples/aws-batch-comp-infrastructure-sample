# The base OS image is Ubuntu noble (v24.04)
# Since we always run the containers on AWS with Amazon Linux,
# we hard-code using the amd64 Linux architecture. This has the benefit of
# reducing the disk size of the generated image.
FROM amd64/ubuntu:noble

# Set up ecs-user, install software dependencies, and set up the SSH daemon
RUN useradd -ms /bin/bash ecs-user \
    # Install software dependencies, including OpenMPI
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt install -y vim python3.12 python3-pip python3.12-venv git openssh-server iproute2 openmpi-bin openmpi-common iputils-ping \
    # Alias `python` and `python3` to the just-installed python3.12
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    # Configure SSH for `ecs-user`
    && mkdir /var/run/sshd \
    && sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd \
    && setcap CAP_NET_BIND_SERVICE=+eip /usr/sbin/sshd \
    && chown -R ecs-user /etc/ssh/ \
    && su - ecs-user -c \
        'ssh-keygen -q -t rsa -f ~/.ssh/id_rsa -N "" \
        && cp ~/.ssh/id_rsa.pub ~/.ssh/authorized_keys \
        && cp /etc/ssh/sshd_config ~/.ssh/sshd_config \
        && sed -i "s/UsePrivilegeSeparation yes/UsePrivilegeSeparation no/g" ~/.ssh/sshd_config \
        && printf "Host *\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config' \
    # Copy SSH keys and config to root so mpirun --allow-run-as-root works
    && mkdir -p /root/.ssh \
    && cp /home/ecs-user/.ssh/id_rsa /home/ecs-user/.ssh/id_rsa.pub /home/ecs-user/.ssh/authorized_keys /home/ecs-user/.ssh/config /root/.ssh/ \
    && chmod 700 /root/.ssh && chmod 600 /root/.ssh/id_rsa

# Alias various directories, and update the PYTHONPATH
ARG SCRIPTING=/opt/amazon/scripting
ENV SCRIPTING=${SCRIPTING}
ARG VENV=${SCRIPTING}/.venv
ENV VENV=${VENV}
ENV PYTHONPATH=${SCRIPTING}:.:

# Copy over the harness Python scripts
COPY --chown=ecs-user scripting ${SCRIPTING}

# Copy test formulas for local solver testing
ARG TEST_FORMULAS=/opt/amazon/test_formulas
ENV TEST_FORMULAS=${TEST_FORMULAS}
COPY --chown=ecs-user examples/formulas ${TEST_FORMULAS}

# Now set up the Python environment and the SSH service
    # Install necessary Python packages in a virtual environment
    # This virtual environment also needs to be activated before running the harness
RUN python3 -m venv ${VENV} \
    # Activate the virtual environment
    # (In Bash, this is usually `source ...`, but Docker uses `/bin/sh` when building images)
    # (See https://www.gnu.org/software/bash/manual/html_node/Bash-Builtins.html#index-source)
    && . ${VENV}/bin/activate \
    # Install the python pacakges
    && python3 -m pip install -r ${SCRIPTING}/requirements-docker.txt \
    # Exit the virtual environment
    && deactivate \
    # Set up SSH
    && service ssh start

# Note that `EXPOSE` doesn't actually expose the port.
# Must run with `-p` at `docker run` and/or expose it in the CDK infrastructure.
EXPOSE 22/tcp

# On entrypoint, run as `ecs-user`, then run the SSH server in the background
# Enter the Python virtual environment we created above
USER ecs-user
ENTRYPOINT /usr/sbin/sshd -D -f /home/ecs-user/.ssh/sshd_config & \
    # Activate the virtual environment (again, using the `source ...` idiom)
    . ${VENV}/bin/activate \
    # Run the entrypoint
    && python3 ${SCRIPTING}/harness/entrypoints/entrypoint.py
