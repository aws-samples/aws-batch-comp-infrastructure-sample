# /bin/sh

# check number arguments
if [[ $# -lt 1 ]]; then
    echo "configure_parallel.sh: needs one argument: <docker_image_name>"
    exit 1
fi

# user config
DOCKER_NETWORK="mallob-test"
HOST_RUNDIR="/home/rbtjones/dev/sat23/docker/runner/experiment"

# config to match other scripts
NODE_TYPE="worker"
DOCKER_RUNDIR="/rundir"

# summary
echo "run_dist_worker.sh, running with"
echo "       node type: $NODE_TYPE"
echo "  docker network: $DOCKER_NETWORK"
echo "    docker image: $1:$NODE_TYPE"
echo "     host rundir: $HOST_RUNDIR"
echo "   docker rundir: $DOCKER_RUNDIR"

# does host directory exist?
if [[ ! -d "$HOST_RUNDIR" ]]; then
    echo "ERROR - unable to reach host run directory '$HOST_RUNDIR'"
    exit 1
fi

# Run docker image. See comments in run_parallel.sh
#
docker run -i --shm-size=32g --name $NODE_TYPE --network $DOCKER_NETWORK --entrypoint bash --rm -v $HOST_RUNDIR:/$DOCKER_RUNDIR -t $1:$NODE_TYPE -c "/competition/init_solver.sh; exec bash"
