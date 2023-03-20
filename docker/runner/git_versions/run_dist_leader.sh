# /bin/sh

# run_dist_leader.sh: Use this script to launch Docker container 
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
HOST_RUNDIR="/home/rbtjones/dev/sat23/docker/runner/experiment"

# script config
NODE_TYPE="leader"
DOCKER_RUNDIR="/rundir"

# summary
echo "run_dist_worker.sh, running with"
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

# create input.json
echo -e "{\n \"formula_file\": \"$DOCKER_RUNDIR/$2\",\n \"worker_node_ips\": [\"leader\", \"worker\"],\n \"timeout_seconds\": \"1000\",\n \"formula_language\": \"smt2\",\n \"solver_argument_list\": []\n}" > "$HOST_RUNDIR/input.json"

# Run docker image. See comments in run_parallel.sh
#
docker run -i --shm-size=32g --name $NODE_TYPE --network $DOCKER_NETWORK --entrypoint bash --rm -v $HOST_RUNDIR:/$DOCKER_RUNDIR -t $1:$NODE_TYPE -c "/competition/init_solver.sh; exec bash"
