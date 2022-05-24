import logging
from threading import TIMEOUT_MAX
import boto3
from botocore.exceptions import ClientError
import os
import argparse
import sys
import json
import time   

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

class SolverTimeoutException(Exception):
    pass


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# maximum retries on non-success (other than timeout)
RETRIES_MAX = 2
TIMEOUT = 1030

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
    parser.add_argument('--clean-first', type=bool, help='Clean the output file prior to run (default: False)')
    parser.add_argument('--purge_queues', type=bool, help='Purge queues and wait one minute prior to start?')
    parser.add_argument('json_file', help='Path to json file containing results')
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


def record_result(input_file_name, result, results): 
    return None

def run_one_problem(problem_queue, result_queue, args, s3_uri): 
    logger = logging.getLogger("log")
    msg = {"s3_uri": s3_uri, "num_workers": args.num_workers}
    msg_str = json.dumps(msg, indent = 4)           

    done = False
    retries = 0
    while not done: 
        problem_queue.put_message(msg_str)
        start_time = time.perf_counter()
        result = result_queue.get_message()

        while result is None:
            logger.info(f"Awaiting completion for file: {s3_uri}")
            end_time = time.perf_counter()
            if end_time - start_time > TIMEOUT:
                raise SolverTimeoutException(f"Client exceeded max time waiting for response ({str(TIMEOUT)}).  Did leader crash?")
            result = result_queue.get_message()

        result_json = json.loads(result.read())
        result.delete()
        print(f"Problem {s3_uri} completed!  result is: {json.dumps(result_json, indent=4)}")

        if result_json["driver"]["timed_out"]:
            done = True
        else:
            result = (result_json["solver"]["output"]["result"]).lower()
            if result == "unsatisfiable" or result == "satisfiable" or retries >= RETRIES_MAX:
                done = True
    
    return result_json

def run_problems(problem_queue, result_queue, input_files, args):
    logger = logging.getLogger("log")
    results = {}
    if os.path.exists(args.json_file) and not args.clean_first:     
        with open(args.json_file, "r") as result_file:
            results = json.load(result_file)

    for input_file in input_files:
        s3_uri = 's3://' + args.s3_bucket + "/" + input_file
        logger.info(f'attempting to solve file: {s3_uri}')

        # skip previously solved files (unless 'clean' flag is true)
        if input_file in results:
            print(f"Problem {s3_uri} is cached from earlier run.  Result is: {json.dumps(results[input_file], indent=4)}")
            continue

        result_json = run_one_problem(problem_queue, result_queue, args, s3_uri)

        # write answer (overwrite existing file)
        results[input_file] = result_json

        with open(args.json_file, "w") as result_file:
            json.dump(results, result_file, indent=4)


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

        if args.purge_queues:
            problem_queue.purge()
            result_queue.purge()
            # recommendation of boto api
            time.sleep(60)

        # create s3 access
        input_files = list_object_keys(s3, args.s3_bucket)
        logger.debug(f'Files to run are: {input_files}')
        run_problems(problem_queue, result_queue, input_files, args)

    except Exception as e:
        logger.error(f"Failure during 'run_satcomp_solver'.  Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
