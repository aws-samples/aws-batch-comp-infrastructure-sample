# Mock solver for testing the test-local command.
# This solver doesn't actually solve SAT/SMT formulas - it determines
# results based on test category passed via solver arguments.
FROM satcomp-infrastructure

# Copy the solver command module
# Note: The build context is the project root
COPY examples/solvers/mock-solver/solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
