# /bin/bash

# run_parallel.sh: Use this script to launch Docker container 
#                  for parallel Mallob. Arguments:
#   $1: docker image name (assumes a "leader" tag)
#   $2: formula file (relative to HOST_RUNDIR)
#   $*: solver arguments (passed directly to solver)

# check number arguments
if [[ $# -lt 2 ]]; then
    echo "run_parallel.sh usage:  <docker_image_name> <formula_file> [solver arguments]"
    exit 1
fi

# read first two command-line arguments
DOCKER_IMAGE_NAME=$1
FORMULA_FILENAME=$2
shift 2
SOLVER_ARGS_SPACED=$*
SOLVER_ARGS="\"${SOLVER_ARGS_SPACED// /\", \"}\""

# user config
DOCKER_NETWORK="mallob-test"
HOST_RUNDIR="/<REPLACE_WITH_ABSOLUTE_PATH>/docker/runner/experiment"
HOST_RUNDIR="/home/rbtjones/dev/sat23/docker/runner/experiment"

# config to match other scripts
NODE_TYPE="leader"
DOCKER_RUNDIR="/rundir"

DOCKER_IMAGE="$DOCKER_IMAGE_NAME:$NODE_TYPE"
HOST_FORMULA_FILE="$HOST_RUNDIR/$FORMULA_FILENAME"
DOCKER_FORMULA_FILE="$DOCKER_RUNDIR/$FORMULA_FILENAME"

# summary
echo "run_parallel.sh, running with"
echo "       node type: $NODE_TYPE"
echo "  docker network: $DOCKER_NETWORK"
echo "    docker image: $DOCKER_IMAGE"
echo "    formula file: $FORMULA_FILENAME"
echo "     host rundir: $HOST_RUNDIR"
echo "   docker rundir: $DOCKER_RUNDIR"

# does host directory exist? 
if [[ ! -d "$HOST_RUNDIR" ]]; then
    echo "ERROR - unable to reach host run directory '$HOST_RUNDIR'"
    exit 1
fi

# does formula file exist?
if [[ ! -f "$HOST_FORMULA_FILE" ]]; then
    echo "ERROR - unable to read formula file '$HOST_FORMULA_FILE'"
    exit 1
fi

#
# create input.json
#
echo -e "{\n \"formula_file\": \"$DOCKER_FORMULA_FILE\",\n \"worker_node_ips\": [\"leader\"],\n \"timeout_seconds\": \"1000\",\n \"formula_language\": \"\",\n \"solver_argument_list\": [$SOLVER_ARGS]\n}" > "$HOST_RUNDIR/input.json"

#
# Run docker image as container. Arguments:
#   -i                    // keep STDIN open even if not attached
#   --shm-size=XXg        // setting up shared memory (for clause DB) 
#                         // default (1G?) is too small
#   --network mallob-test // use the Docker bridge network called 'mallob-test'
#   --entrypoint bash     // when the container starts, it runs bash
#   --rm                  // remove the docker container when exiting
#   -v                    // mount $HOST_RUNDIR in the host filesystem at '/$DOCKER_RUNDIR' in docker image
#   -t                    // Docker image name for leader (script hard-codes 'leader' tag)
#   -c <bash_command>     // gets passed to bash shell

docker run -i --shm-size=32g --name $NODE_TYPE --network $DOCKER_NETWORK --entrypoint bash --rm -v $HOST_RUNDIR:$DOCKER_RUNDIR -t $DOCKER_IMAGE -c "/competition/init_mallob.sh; exec bash"