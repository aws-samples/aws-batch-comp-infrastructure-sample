#!/usr/bin/env bash

set -x

if [ $# -ne 2 ] ; then
    echo "USAGE: "
    echo "build-job-queue.sh PROFILE PROJECT_NAME"
    echo "where: "
    echo "   PROFILE is a AWS CLI profile with administrator access to the account"
    echo "   PROJECT_NAME is the name used for the project in build-solver-pipeline.sh"
    exit 1
fi

aws --profile $1 cloudformation create-stack --stack-name job-queue-$2 \
--template-body file://build-job-queue.yaml --capabilities CAPABILITY_IAM \
--parameters \
  ParameterKey=ProjectName,ParameterValue=$2

# Wait for bucket to finish creating...
# echo waiting for bucket to create.
# sleep 30
