#!/usr/bin/env bash

set -x

aws --profile $1 ecs run-task --launch-type FARGATE --cluster $2 --task-definition $3 --network-configuration \
"{
   \"awsvpcConfiguration\": {
      \"subnets\": [\"$4\"],
      \"securityGroups\": [\"$5\"],
      \"assignPublicIp\": \"ENABLED\"
   }
}" \
--overrides \
"{
  \"containerOverrides\": [{
    \"name\": \"$8\",
    \"environment\": [
        {
            \"name\":\"COMP_S3_PROBLEM_PATH\",
            \"value\": \"shared-entries/$6\"
        },
        {
            \"name\":\"AWS_BATCH_JOB_NODE_INDEX\",
            \"value\": \"0\"
        },
        {
            \"name\":\"NUM_PROCESSES\",
            \"value\": \"$7\"
        },
        {
            \"name\":\"AWS_BATCH_JOB_NUM_NODES\",
            \"value\": \"$7\"
        },
        {
            \"name\":\"S3_BKT\",
            \"value\":\"sat-comp-2020\"
        }
    ]
  }]
}
"
