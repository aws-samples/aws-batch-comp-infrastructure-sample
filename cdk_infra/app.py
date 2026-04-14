#!/usr/bin/env python3

import json
import os
from pathlib import Path
from typing import List, Tuple

import aws_cdk as cdk
import common.pathing as pathing
from common import CdkSolver, ResourceNamer
from solver_constructs import (
    EcrRepoStack,
    LogGroupStack,
    S3ResultsStack,
    SolverStack,
    SolverVpcStack,
)

################################################################################


def get_project_and_solvers() -> Tuple[str, List[CdkSolver]]:
    SCRIPT_DIR = pathing.normalize_path(os.path.dirname(__file__))
    solvers_file: Path = SCRIPT_DIR / "solvers.json"

    if solvers_file.exists() and solvers_file.is_file():
        with open(solvers_file, "r") as f:
            solvers_obj = json.load(f)
        project = solvers_obj["project"]
        solvers = [CdkSolver.from_dict(s) for s in solvers_obj["solvers"]]
    else:
        project = "satcomp25"
        solvers = []

    return project, solvers


################################################################################

if __name__ == "__main__":
    project, solvers = get_project_and_solvers()
    rn = ResourceNamer(project)
    app = cdk.App()

    # Create the global resources, shared by all solvers
    S3ResultsStack(app, rn.get_results_bucket_stack_name(), rn)
    EcrRepoStack(app, rn.get_ecr_repo_stack_name(), rn)

    # We save a reference to the VPC stack to give to the solver stacks.
    # This is explicitly recommended by the CDK docs for `Vpc.from_lookup()`.
    # See https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ec2/Vpc.html#aws_cdk.aws_ec2.Vpc.from_lookup
    vpc = SolverVpcStack(app, rn.get_vpc_stack_name(), project=project)

    for solver in solvers:
        rn.set_solver(solver.name)
        LogGroupStack(app, rn.get_log_group_stack_name(), rn)
        SolverStack(app, rn.get_solver_stack_name(), vpc, rn, solver)

    app.synth()
