# /bin/sh

# check number arguments
if [[ $# -lt 1 ]]; then
    echo "configure_parallel.sh: needs one argument: <docker_image_name>"
    exit 1
fi

# user config
DOCKER_NETWORK="mallob-test"


# config to match other scripts
NODE_TYPE="worker"

# summary
echo "run_dist_worker.sh, running with"
echo "       node type: $NODE_TYPE"
echo "  docker network: $DOCKER_NETWORK"
echo "    docker image: $1:$NODE_TYPE"

# Run docker image. See comments in run_parallel.sh
#
docker run -i --shm-size=32g --name $NODE_TYPE --network $DOCKER_NETWORK --entrypoint bash --rm -t $1:$NODE_TYPE -c "/competition/init_mallob.sh; exec bash"