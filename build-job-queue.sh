#!/usr/bin/env bash

set -x

if [ $# -ne 3 ] ; then
    echo "USAGE: "
    echo "build-job-queue.sh PROFILE REGION PROJECT_NAME"
    echo "where: "
    echo "   PROFILE is a AWS CLI profile with administrator access to the account"
    echo "   PROJECT_NAME is the name used for the project in build-solver-pipeline.sh"
    exit 1
fi

aws --profile $1 cloudformation create-stack --stack-name job-queue-$3 \
--template-body file://build-job-queue.yaml --capabilities CAPABILITY_IAM \
--parameters \
  ParameterKey=ProjectName,ParameterValue=$3 ParameterKey=AvailZoneId,ParameterValue=a

# Wait for bucket to finish creating...
# echo waiting for bucket to create.
# sleep 30
