#!/bin/bash

# start sshd
/usr/sbin/sshd -D -f /home/ecs-user/.ssh/sshd_config &

