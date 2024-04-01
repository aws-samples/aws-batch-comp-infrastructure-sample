FROM ubuntu:20.04
RUN useradd -ms /bin/bash ecs-user
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt install -y python3-pip git openssh-server openssh-server iproute2 openmpi-bin openmpi-common iputils-ping \
    && mkdir /var/run/sshd \
    && sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd \
    && setcap CAP_NET_BIND_SERVICE=+eip /usr/sbin/sshd \
    && chown -R ecs-user /etc/ssh/ \
    && su - ecs-user -c \
        'ssh-keygen -q -t rsa -f ~/.ssh/id_rsa -N "" \
        && cp ~/.ssh/id_rsa.pub ~/.ssh/authorized_keys \
        && cp /etc/ssh/sshd_config ~/.ssh/sshd_config \
        && sed -i "s/UsePrivilegeSeparation yes/UsePrivilegeSeparation no/g" ~/.ssh/sshd_config \
        && printf "Host *\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config'