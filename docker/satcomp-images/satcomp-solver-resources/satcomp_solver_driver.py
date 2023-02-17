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


class SolverTimeoutException(Exception):
    pass


class S3ProblemStore:
    """Class to represent S3 storage location"""

    def __init__(self, s3_resource, formula_bucket, logger):
        self.s3_resource = s3_resource
        self.logger = logger
        self.formula_bucket = formula_bucket

    def list_cnf_file_s3_path_pairs(self):
        try:
            self.logger.debug(f'Attempting to list files for bucket {self.formula_bucket}')
            bkt = self.s3_resource.Bucket(self.formula_bucket)
            pairs = [(bkt_object.key, f's3://{self.formula_bucket}/{bkt_object.key}') for bkt_object in bkt.objects.all()]
            return pairs
        except ClientError as e:
            self.logger.error(f"Failed to list s3 bucket objects from {self.formula_bucket}")
            self.logger.exception(e)
            raise

    def get_bucket(self):
        return self.formula_bucket

    @staticmethod
    def get_s3_file_system(session, formula_bucket, logger):
        s3 = session.resource('s3')
        return S3ProblemStore(s3, formula_bucket, logger)



logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# maximum retries on non-success (other than timeout)
RETRIES_MAX = 2
TIMEOUT = 1030


class ProblemRunner: 
    """Class to run a problem set through a distributed solver"""
    def __init__(self, problem_queue, result_queue, s3_problem_store, args, logger):
        self.num_workers = args.num_workers
        self.clean_first = args.clean_first
        self.json_file = args.json_file
        self.s3_problem_store = s3_problem_store
        self.problem_queue = problem_queue
        self.result_queue = result_queue
        self.logger = logger


    def run_one_problem(self, s3_uri): 
        msg = {"s3_uri": s3_uri, "num_workers": self.num_workers}
        msg_str = json.dumps(msg, indent = 4)           

        done = False
        retries = 0
        while not done: 
            self.problem_queue.put_message(msg_str)
            start_time = time.perf_counter()
            result = self.result_queue.get_message()

            while result is None:
                self.logger.info(f"Awaiting completion for file: {s3_uri}")
                end_time = time.perf_counter()
                if end_time - start_time > TIMEOUT:
                    raise SolverTimeoutException(f"Client exceeded max time waiting for response ({str(TIMEOUT)}).  Did leader crash?")
                result = self.result_queue.get_message()

            result_json = json.loads(result.read())
            result.delete()
            print(f"Problem {s3_uri} completed!  result is: {json.dumps(result_json, indent=4)}")

            if result_json["driver"]["timed_out"]:
                done = True
            else:
                result = (result_json["solver"]["output"]["result"]).lower()
                retries = retries + 1
                
                if result == "unsatisfiable" or result == "satisfiable" or retries >= RETRIES_MAX:
                    done = True
        
        return result_json

    def run_problems(self):
        results = {}
        if os.path.exists(self.json_file) and not self.clean_first:     
            with open(self.json_file, "r") as result_file:
                results = json.load(result_file)

        for (input_file, s3_uri) in self.s3_problem_store.list_cnf_file_s3_path_pairs():
            self.logger.info(f'attempting to solve file: {s3_uri}')

            # skip previously solved files (unless 'clean' flag is true)
            if input_file in results:
                print(f"Problem {s3_uri} is cached from earlier run.  Result is: {json.dumps(results[input_file], indent=4)}")
                continue

            result_json = self.run_one_problem(s3_uri)

            # write answer (overwrite existing file)
            results[input_file] = result_json

            with open(self.json_file, "w") as result_file:
                json.dump(results, result_file, indent=4)

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
    parser.add_argument('--purge-queues', type=bool, help='Purge queues and wait one minute prior to start?')
    parser.add_argument('json_file', help='Path to json file containing results')
    return parser

def main():
    logger = logging.getLogger("satcomp_log")
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
    
        # create AWS access objects
        problem_queue = SqsQueue.get_sqs_queue_from_session(session, args.problem_queue)
        result_queue = SqsQueue.get_sqs_queue_from_session(session, args.result_queue)
        s3_problem_store = S3ProblemStore.get_s3_file_system(session, args.s3_bucket, logger)
        problem_runner = ProblemRunner(problem_queue, result_queue, s3_problem_store, args, logger)
        
        if args.purge_queues:
            logger.info('Purging problem and result queues')
            problem_queue.purge()
            result_queue.purge()
            # recommendation of boto api
            time.sleep(60)

        problem_runner.run_problems()

    except Exception as e:
        logger.error(f"Failure during 'run_satcomp_solver'.  Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
