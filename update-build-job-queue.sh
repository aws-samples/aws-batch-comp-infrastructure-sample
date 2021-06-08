#!/usr/bin/env bash

set -x

if [ $# -ne 2 ] ; then
    echo "USAGE: "
    echo "job-queue.sh PROFILE PROJECT_NAME"
    echo "where: "
    echo "   PROFILE is a AWS CLI profile with administrator access to the account"
    echo "   PROJECT_NAME is the name used for the project in build-solver-pipeline.sh"
    exit 1
fi

#aws --profile mww cloudformation create-stack --stack-name create-$1-bucket \
#--template-body file://create_s3_bucket.yaml
#--parameters \
#  ParameterKey=S3BucketSuffix,ParameterValue=$1 \
#  ParameterKey=S3BucketType,ParameterValue=$1-codepipeline-bucket

# Wait for bucket to finish creating...
# echo waiting for bucket to create.
# sleep 30

aws --profile $1 cloudformation update-stack --stack-name job-queue-$2 \
--template-body file://job-queue.yaml --capabilities CAPABILITY_IAM \
--parameters \
  ParameterKey=ProjectName,ParameterValue=$2