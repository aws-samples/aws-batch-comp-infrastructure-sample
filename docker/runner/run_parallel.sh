# /bin/bash

# run_parallel.sh: Use this script to launch Docker container 
#                     for parallel Mallob. Arguments:
#   $1: docker image name (assumes a "leader" tag)
#   $2: formula file (relative to HOST_RUNDIR)

# check number arguments
if [[ $# -lt 2 ]]; then
    echo "run_parallel.sh: needs two arguments: <docker_image_name> <formula file>"
    exit 1
fi

# user config
DOCKER_NETWORK="mallob-test"
HOST_RUNDIR="/home/rbtjones/dev/mallob/satcomp-infrastructure/docker/runner/experiment"
DOCKER_RUNDIR="/rundir"

# script config
NODE_TYPE="leader"
SSHD_CMD="/usr/sbin/sshd -D -f /home/ecs-user/.ssh/sshd_config"

# summary
echo "run_parallel.sh, running with"
echo "       node type: $NODE_TYPE"
echo "  docker network: $DOCKER_NETWORK"
echo "    docker image: $1:$NODE_TYPE"
echo "    formula file: $HOST_RUNDIR/$2"
echo "     host rundir: $HOST_RUNDIR"
echo "   docker rundir: $DOCKER_RUNDIR"

# does host directory exist? 
if [[ ! -d "$HOST_RUNDIR" ]]; then
    echo "ERROR - unable to reach host run directory '$HOST_RUNDIR'"
    exit 1
fi

# does formula file exist?
if [[ ! -f "$HOST_RUNDIR/$2" ]]; then
    echo "ERROR - unable to read formula file '$HOST_RUNDIR/$2'"
    exit 1
fi

#
# create input.json
#
echo -e "{\n\"formula_file\": \"$DOCKER_RUNDIR/$2\",\n\"worker_node_ips\": [\"leader\"]\n}" > "$HOST_RUNDIR/input.json"

# user instructions
echo ""
echo "After Docker launch, run: "
echo "  /usr/sbin/sshd -D -f /home/ecs-user/.ssh/sshd_config &"
echo "  /competition/solver $DOCKER_RUNDIR"
echo ""

#
# Run docker image as container. Arguments:
#   -i                    // keep STDIN open even if not attached
#   --shm-size=XXg        // setting up shared memory (for clause DB) 
#                         // default (1G?) is too small
#   --network mallob-test // use the Docker bridge network called 'mallob-test'
#   --entrypoint bash     // when the container starts, it runs bash; nothing
#                         // happens until we call a solver script from inside the container
#   --rm                  // remove the docker container when exiting
#   -v                    // mount $HOST_RUNDIR in the host filesystem at '/$DOCKER_RUNDIR' in docker image
#   -t                    // Docker image name for leader (script hard-codes 'leader' tag)
#

# echo docker run -i --shm-size=32g --name $NODE_TYPE --network mallob-test --entrypoint "bash --init-file <(echo $SSHD_CMD)" --rm -v $HOST_RUNDIR:/rundir  -t $1:$NODE_TYPE
docker run -i --shm-size=32g --name $NODE_TYPE --network $DOCKER_NETWORK --entrypoint bash --rm -v $HOST_RUNDIR:/$DOCKER_RUNDIR -t $1:$NODE_TYPE