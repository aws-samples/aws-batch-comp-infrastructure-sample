from common.ec2_instance import SolverEc2Instance
from common.json_to_python import JsonToPythonObject

################################################################################


class CdkSolver(JsonToPythonObject):

    EC2_INSTANCE_KEY = "ec2_instance_type"
    DISK_KEY = "disk_size"
    IS_DIST_KEY = "is_distributed"
    NUM_WORKERS_KEY = "num_worker_nodes_per_leader"

    # AWS configuration option keys
    CONFIG_KEYS = [
        EC2_INSTANCE_KEY,
        DISK_KEY,
        IS_DIST_KEY,
        NUM_WORKERS_KEY,
    ]

    # As of August 2025, we are using the ECS-optimized Amazon Linux 2023 AMI.
    # This AMI needs at least 30 GB of EBS disk space, according to:
    # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-optimized_AMI.html
    # If the underlying AMI ever changes, the minimum disk size will need to be updated.
    # (To change the AMI, edit the `machine_image` for the `launchTemplate` in `solver_stack.py`)
    MIN_DISK_SIZE = 30

    def __init__(
        self,
        name: str,
        ec2_instance_type: str | SolverEc2Instance,
        disk_size: float,
        is_distributed: bool,
        num_workers: int | str = 0,
        author: str | None = None,
    ):
        self.name = name
        self.author = author
        if isinstance(ec2_instance_type, SolverEc2Instance):
            self.ec2_instance_type = ec2_instance_type
        else:
            self.ec2_instance_type = SolverEc2Instance.from_str(ec2_instance_type)

        self.disk_size = float(disk_size)
        if self.disk_size < self.MIN_DISK_SIZE:
            raise ValueError(f'Disk size for solver "{self.name}" must be at least {self.MIN_DISK_SIZE} GB')

        self.is_distributed = is_distributed
        self.is_parallel = not self.is_distributed
        self.num_workers = int(num_workers)
        assert self.is_parallel or self.num_workers > 0

    def equals(self, other: "CdkSolver") -> bool:
        return (
            self.name == other.name
            and self.ec2_instance_type == other.ec2_instance_type
            and self.disk_size == other.disk_size
            and self.is_distributed == other.is_distributed
            and self.num_workers == other.num_workers
            and self.author == other.author
        )

    @classmethod
    def from_dict(cls, d: dict) -> "CdkSolver":
        return CdkSolver(
            name=d["name"],
            ec2_instance_type=d[cls.EC2_INSTANCE_KEY],
            disk_size=d[cls.DISK_KEY],
            is_distributed=d[cls.IS_DIST_KEY],
            num_workers=d.get(cls.NUM_WORKERS_KEY, 0),
            author=d.get("author"),
        )

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            self.EC2_INSTANCE_KEY: str(self.ec2_instance_type),
            self.DISK_KEY: self.disk_size,
            self.IS_DIST_KEY: self.is_distributed,
            self.NUM_WORKERS_KEY: self.num_workers,
        }

        if self.author is not None:
            d["author"] = self.author

        return d
