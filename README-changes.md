# Changes from 2022 SAT/SMT-Comp Interactions

The fundamental architecture for the SAT/SMT competition is unchanged from 2022.  However, based on feedback from competitors in 2022, we have made some small changes to how the infrastructure interacts with the solvers provided by each team through the `input.json` file and `solver-out.json` files.

## Changes to input.json

We have enriched the `input.json` file to allow solvers to be invoked with different arguments / solver names to allow testing of different strategies without rebuilding the container, and to specify a timeout for the solver.

The 2022 format for input.json was as follows: 

```text
{
    "problem_path": "/mount/efs/problem.cnf",
    "worker_node_ips": ["192.158.1.38", "192.158.2.39", ...]
}
```

In 2023, we have expanded this format to: 

```text
{
  "formula_file": "/mount/efs/problem.cnf",
  "formula_language": "DIMACS", 
  "solver_argument_list": ["-p", "another_arg"],
  "timeout_seconds": 10,
  "worker_node_ips": ["192.158.1.38", "192.158.2.39", ...]
}
```

where: 
* `formula_file` is the path to the SAT/SMT problem to be solved.
* `formula_language` is the encoding of the problem (currently we use DIMACS for SAT-Comp and SMTLIB2 for SMT-Comp).  This field is optional and can be ignored by the solver.
* `solver_argument_list` allows passthrough of arguments to the solver.  This allows you to try different strategies without rebuilding your docker container by varying the arguments.
* `timeout_seconds` is the timeout for the solver.  It will be enforced by the infrastructure; a solver that doesn't complete within the timeout will be terminated.
* `worker_node_ips` is unchanged; for cloud solvers, it is the list of worker nodes.  For parallel solvers this field will always be the empty list.

The executable / python file that starts the solver should be updated to support this new format.

## Changes to solver_out.json

The 2022 format for solver_out.json was as follows:

```text
{
  "return_code": Number, // of running the solve command
  "result": String,      // Should be one of {"SAT", "UNSAT", "UNKNOWN", "ERROR"}
  "artifacts": {
    "stdout_path": String, // Where to find the stdout of the solve run
    "stderr_path": String  // Where to find the stderr of the solve run
  }
}
```

In 2023, we have modified the format to:

```text
{
  "return_code": int,      // The return code for the solver.
  "artifacts": {
    "stdout_path": String, // Where to find the stdout of the solve run
    "stderr_path": String  // Where to find the stderr of the solve run
  }
}
```

where:
* `return_code` is the return code for the solver.  **N.B.**: Unlike the 2022 format, the return_code in `solver_out.json` will determine the satisfiability of the problem for the solver: A return code of 10 indicates SAT, 20 indicates UNSAT, 0 indicates UNKNOWN, and all other return codes indicate an error.
* `stdout_path` is the path to the stdout log.
* `stderr_path` is the path to the stderr log.

The Mallob example solver has been updated to support the new format, so you can examine these changes by examining the leader solver python file [here](docker/mallob-images/leader/solver).  This file is compatible with the new format, but does not use the `formula_language`, `timeout_seconds` or `solver_argument_list` fields.