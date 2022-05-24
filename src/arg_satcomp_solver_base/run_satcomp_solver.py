import logging
import boto3
from botocore.exceptions import ClientError
import os
import socket
import subprocess
import argparse
import sys
import csv
import json   

sys.path.append('../')
from arg_satcomp_solver_base.sqs_queue.sqs_queue import SqsQueue


# inputs: s3 bucket where problems are found
#         solver name
# output: csv file containing result for each problem.
#         file name is: <solver_name>.csv

#         simplest thing would be just a list of the json results. 
#         but...how do I "tie it off" on failure?
#         I could just wait 1100 seconds; if there is no response then kill it.
#         But what if I want to kill it?
#         It would probably be better to just write a .csv file.
#         I bet python has libraries for this!

# How about restarts?
#   read the .csv file into a dict for the key (filename) to see if it has previously reached a conclusive answer.

# Program structure:
#   Create a class for the result data type: reading and writing.
# 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a SATComp solver through all files in a bucket"
    )
    parser.add_argument(
        "-v", "--version", action="version",
        version = f"{parser.prog} version 0.1.0"
    )
    parser.add_argument('--profile', required = True, help = "AWS profile")
    parser.add_argument('--problem-queue', required=True, type=str, help='Name of the problem SQS queue (sends jobs to solver) ')
    parser.add_argument('--result-queue', required=True, type=str, help='Name of the result SQS queue (receives outputs from solver) ')
    parser.add_argument('--s3-bucket', required=True, type=str, help='Name of the s3 bucket')
    parser.add_argument('--num-workers', required=True, type=int, help='Number of workers in the cluster')
    parser.add_argument('--verbose', type=int, help='Set the verbosity level of output: 0 = ERROR, 1 = INFO, 2 = DEBUG (default: 0)')
    parser.add_argument('--clean-first', type=bool, help='Clean the output directories prior to run (default: False)')
    parser.add_argument('csv_file', help='Path to output csv file')
    # parser.add_argument('--skip-overlap', type=bool, help='Skip the overlap portion of the analysis')
    return parser

def list_object_keys(s3_resource, problem_bucket: str):
    logger = logging.getLogger("log")
    try:
        logger.debug(f'Attempting to list files for bucket {problem_bucket}')
        bkt = s3_resource.Bucket(problem_bucket)
        return [bkt_object.key for bkt_object in bkt.objects.all()]
    except ClientError as e:
        logger.error(f"Failed to list s3 bucket objects from {problem_bucket}")
        logger.exception(e)
        raise



def run_problems(problem_queue, result_queue, bucket, input_files, csv_file, num_workers):
    logger = logging.getLogger("log")

    for input_file in input_files:
        # TODO: add check for previous run from .csv file.

        s3_uri = 's3://' + bucket + "/" + input_file
        logger.info(f'attempting to solve file: {s3_uri}')
        done = False
        while not done: 
            msg = {"s3_uri": s3_uri, "num_workers": num_workers}
            msg_str = json.dumps(msg, indent = 4)           
            problem_queue.put_message(msg_str)
            result = result_queue.get_message()
            while result is None:
                logger.info(f"Awaiting completion for file: {s3_uri}")
                result = result_queue.get_message()

            result_json = json.loads(result.read())
            print(f"Problem {s3_uri} completed!  result is: {json.dumps(result_json, indent=4)}")

            # TODO: Add different result cases here & add to result .csv file.
            done = True


def main():
    logger = logging.getLogger("log")
    try:
        parser = init_argparse()
        args = parser.parse_args()
        
        if args.verbose and args.verbose > 0:
            if args.verbose == 1:
                logger.setLevel(logging.INFO)
            elif args.verbose >= 2:
                logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.ERROR)

        logger.debug('command line arguments: ' + str(args))
        
        session = boto3.Session(profile_name=args.profile)
        s3 = session.resource('s3')
    
        # create queue access
        problem_queue = SqsQueue.get_sqs_queue_from_session(session, args.problem_queue)
        result_queue = SqsQueue.get_sqs_queue_from_session(session, args.result_queue)

        # create s3 access
        input_files = list_object_keys(s3, args.s3_bucket)
        logger.debug(f'Files to run are: {input_files}')
        run_problems(problem_queue, result_queue, args.s3_bucket, input_files, args.csv_file, args.num_workers)

    except Exception as e:
        logger.error(f"Failed to run solver.  Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
