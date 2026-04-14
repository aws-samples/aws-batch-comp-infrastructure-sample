"""Job management commands for submitting, processing, and purging solver jobs."""

from harness.aws_shim import S3FileSystem, SqsQueue
from runner.commands.base import CommandContext, CommandHandler
from runner.runner_jobs import SolverJobManager


class SubmitCommand(CommandHandler):
    """Submit formula jobs to solver input queues."""

    def __init__(self, ctx: CommandContext, job_manager: SolverJobManager, logger=None):
        """Initialize the submit command.

        Args:
            ctx: CommandContext with AWS clients and config
            job_manager: SolverJobManager for job operations
            logger: Optional logger instance
        """
        super().__init__(ctx, logger)
        self.jm = job_manager

    def execute(self, **kwargs) -> int:
        """Submit jobs from the jobs config to solver queues.

        Returns:
            0 on success, 1 on error
        """
        self.logger.info("submit: Submit formula jobs to the solver input queues")

        s3 = S3FileSystem.get_s3_file_system_from_session(self.ctx.boto3_session)
        project = self.ctx.project
        aws_solvers = self.ctx.aws_solvers
        rn = self.ctx.rn

        num_files = self.jm.prepare_jobs(s3, project.solver_type)
        if num_files == 0:
            self.logger.error("Error: No matching formula files were found")
            return 1

        for solver in aws_solvers:
            rn.set_solver(solver)
            q_in_name = rn.get_sqs_input_queue_name()
            q_in = SqsQueue.get_sqs_queue_from_session(self.ctx.boto3_session, q_in_name)
            self.jm.submit_jobs(solver, q_in)

        return 0


class ProcessCommand(CommandHandler):
    """Process solver results from output queues."""

    def __init__(self, ctx: CommandContext, job_manager: SolverJobManager, logger=None):
        """Initialize the process command.

        Args:
            ctx: CommandContext with AWS clients and config
            job_manager: SolverJobManager for job operations
            logger: Optional logger instance
        """
        super().__init__(ctx, logger)
        self.jm = job_manager

    def execute(self, **kwargs) -> int:
        """Process results from solver output queues.

        Returns:
            0 on success
        """
        aws_solvers = self.ctx.aws_solvers
        rn = self.ctx.rn

        self.jm.make_results_dir()
        for solver in aws_solvers:
            self.logger.info(f"Processing results for solver {solver}...")
            rn.set_solver(solver)
            q_out_name = rn.get_sqs_output_queue_name()
            q_out = SqsQueue.get_sqs_queue_from_session(self.ctx.boto3_session, q_out_name)
            self.jm.process_jobs(q_out)

        return 0


class PurgeCommand(CommandHandler):
    """Purge all jobs from solver input queues."""

    def execute(self, **kwargs) -> int:
        """Purge the input queue for all solvers.

        Returns:
            0 on success
        """
        aws_solvers = self.ctx.aws_solvers
        rn = self.ctx.rn

        for solver in aws_solvers:
            self.logger.info(f"Purging the input queue of jobs for solver {solver}...")
            rn.set_solver(solver)
            q_in_name = rn.get_sqs_input_queue_name()
            q_in = SqsQueue.get_sqs_queue_from_session(self.ctx.boto3_session, q_in_name)
            q_in.purge()

        return 0
