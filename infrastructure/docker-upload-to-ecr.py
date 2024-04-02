#!/usr/bin/env python3
import argparse
import logging
import boto3
from botocore.exceptions import ClientError, ProfileNotFound
import sys
import subprocess
import re

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Runner")
logger.setLevel(logging.INFO)


class STS: 
    def __init__(self, sts_client) -> None:
        self.sts = sts_client

    def get_account_number(self) -> str: 
        try: 
            return self.sts.get_caller_identity()["Account"]
        except Exception as e:
            logger.error(f"Failed to get profile account number: {e}")
            raise e

def arg_parser() -> dict: 
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required = False, help = "AWS profile")
    parser.add_argument('--project', required = False, default = 'comp24', help = "ADVANCED USERS ONLY: Name of the project (default: 'comp24').")
    parser.add_argument('--leader', required = False, help = "Docker tag name of the leader container")
    parser.add_argument('--worker', required = False, help = "Docker tag name of the worker container (only for cloud track)")
    
    args = parser.parse_args()

    # argument checking.    
    # matcher = re.compile(allowable_project_names_mask)
    if not re.match(r"^[a-z]([a-z\d\/_-])*$", args.project): 
        logger.error(f"Invalid project name '{args.project}'.")
        logger.error(f"Project names must start with a lowercase letter and can consist only of lowercase numbers, digits, '/', '_', or '-' characters.")
        sys.exit(-1)
    
    if not (args.leader or args.worker):
        logger.error(f"Neither leader or worker image specified...nothing to upload!")
        sys.exit(-1)

    return args


def main() -> None: 
    args = arg_parser()

    try:
        session = boto3.Session(profile_name=args.profile)
    except ProfileNotFound as e:
        logger.error(f"Unable to create AWS session.  Profile '{profile}' not found.  Please double check that this profile is set up in the ~/.aws/config file")
        sys.exit(1)
    if not session.region_name:
        logger.error(f"Profile does not have a region defined.  Please add a region (recommend: us-east-1) to profile '{profile}' in the ~/.aws/config file")
        sys.exit(1)

     # link to AWS services
    sts_client = session.client('sts')
    sts = STS(sts_client)

    # in order to make the call, I need: 
    # - the account #
    # - the region
    # - the profile
    # - the project id
    # - the leader container
    # - the worker container

    account_number = sts.get_account_number()
    region = session.region_name
    project_name = args.project
    profile_args = ['-p', args.profile] if args.profile else []
    leader_args = ['-l', args.leader] if args.leader else []
    worker_args = ['-w', args.worker] if args.worker else []
    

    # run the shell script file to set it up.
    cmd = ' '.join(['./ecr-push-internal.sh', \
        '-j', project_name, \
        '-a', str(account_number), \
        '-r', region] + \
        profile_args + leader_args + worker_args)

    logger.info(f"About to run: { cmd }")
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 1: 
        logger.error("The login command to ECR failed.  Please double check that you have the correct rights in the profile.")
        exit(1)
    elif result.returncode == 2:
        logger.error(f"The attempt to tag the leader image failed.  Please make sure that you have a local leader image associated with {args.leader}.")
        exit(2)
    elif result.returncode == 3:
        logger.error(f"The attempt to upload the leader failed.  Please make sure that there is a repository associated with {project_name}.")
        exit(3)
    elif result.returncode == 4:
        logger.error(f"The attempt to tag the worker image failed.  Please make sure that you have a local worker image associated with {args.worker}.")
        exit(4)
    elif result.returncode == 3:
        logger.error(f"The attempt to upload the worker failed.  Please make sure that there is a repository associated with {project_name}.")
        exit(5)
    elif result.returncode == 0:
        logger.info("Upload succeeded. ")
        exit(0)
    else:
        logger.error(f"Unexpected return code: {result.returncode} from ecr-push-internal.sh; exiting")
        exit(6)

if __name__ == "__main__":
    main()