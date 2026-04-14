#!/user/bin/env python3

"""A shim to call the correct `run()` function, based on env variables."""

import leader_entrypoint as leader
import worker_entrypoint as worker
from common import LoggingManager
from common.misc import get_local_ip_address
from common.solver_env import SolverEnvironment

################################################################################

if __name__ == "__main__":
    lm = LoggingManager()
    logger = lm.get_logger("Entrypoint")
    logger.info(f"Local IP address: {get_local_ip_address()}")

    senv = SolverEnvironment.from_env()
    logger.info(f"Environment variables are: {senv.to_dict()}")

    if senv.is_leader:
        logger.info("I am a leader. About to call `leader.run()`")
        leader.run(senv)
    else:
        logger.info("I am a worker. About to call `worker.run()`.")
        worker.run(senv)
