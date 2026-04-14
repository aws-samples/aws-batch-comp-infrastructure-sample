from enum import Enum

# The percentage of "total memory" on the EC2 instance reserved for the user.
# This value is needed because Amazon's Elastic Container Service will refuse
# to start a container if the underlying EC2 instance doesn't have enough RAM.
# Thus, our soft memory limit is below the "maximum" to prevent false refusals.
USER_MEM_PERCENTAGE = 15 / 16


def gb_to_mb(x: int, apply_user_mem_percentage: bool = False) -> int:
    if apply_user_mem_percentage:
        return round(USER_MEM_PERCENTAGE * x * 1024)
    else:
        return x * 1024


def user_gb_to_mb(x: int) -> int:
    return gb_to_mb(x, apply_user_mem_percentage=True)


class SolverEc2Instance(Enum):
    """
    Hardware specs for the EC2 instance types that run solvers on ECS.

    Each enum is a triple of:
    - The EC2 instance string running the ECS Docker container.
    - The Docker container's soft-memory limit, in megabytes.
    - Size of `/dev/shm` region, in megabytes (see `man shm_open`).
      On Linux, the default size is half of RAM.

    Access these fields with `.instance_str()` or `str()`,
    `.soft_mem_limit_in_mib()`,
    and `shm_in_mib()`, respectively.

    Many of these hardware/memory specs are pulled from Amazon's documentation.
    For more information, see: https://aws.amazon.com/ec2/instance-types/

    Note for future developers:
    This enum defines a small subset of the actual available EC2 instance types.
    However, you must be careful when adding new ones: our ECS containers run
    Amazon Linux 2023 with an x86_64 architecture, meaning that an Intel
    processor is expected. When adding options, make sure that the instance's
    underlying architecture is compatible with the images we want to run.
    """

    # C6A instance family
    C6A_LARGE = ("c6a.large", user_gb_to_mb(4), gb_to_mb(2))
    C6A_XLARGE = ("c6a.xlarge", user_gb_to_mb(8), gb_to_mb(4))
    C6A_2XLARGE = ("c6a.2xlarge", user_gb_to_mb(16), gb_to_mb(8))
    C6A_4XLARGE = ("c6a.4xlarge", user_gb_to_mb(32), gb_to_mb(16))
    C6A_8XLARGE = ("c6a.8xlarge", user_gb_to_mb(64), gb_to_mb(32))
    C6A_12XLARGE = ("c6a.12xlarge", user_gb_to_mb(96), gb_to_mb(48))
    C6A_16XLARGE = ("c6a.16xlarge", user_gb_to_mb(128), gb_to_mb(64))
    C6A_24XLARGE = ("c6a.24xlarge", user_gb_to_mb(192), gb_to_mb(96))
    C6A_32XLARGE = ("c6a.32xlarge", user_gb_to_mb(256), gb_to_mb(128))
    C6A_48XLARGE = ("c6a.48xlarge", user_gb_to_mb(384), gb_to_mb(192))
    C6A_METAL = ("c6a.metal", user_gb_to_mb(384), gb_to_mb(192))

    # M6i instance family - 3rd generation Intel Xeon Scalable (Ice Lake)
    M6I_LARGE = ("m6i.large", user_gb_to_mb(8), gb_to_mb(4))
    M6I_XLARGE = ("m6i.xlarge", user_gb_to_mb(16), gb_to_mb(8))
    M6I_2XLARGE = ("m6i.2xlarge", user_gb_to_mb(32), gb_to_mb(16))
    M6I_4XLARGE = ("m6i.4xlarge", user_gb_to_mb(64), gb_to_mb(32))
    M6I_8XLARGE = ("m6i.8xlarge", user_gb_to_mb(128), gb_to_mb(64))
    M6I_16XLARGE = ("m6i.16xlarge", user_gb_to_mb(256), gb_to_mb(128))
    M6I_32XLARGE = ("m6i.32xlarge", user_gb_to_mb(512), gb_to_mb(256))

    # M7i instance family -
    M7I_LARGE = ("m7i.large", user_gb_to_mb(8), gb_to_mb(4))
    M7I_XLARGE = ("m7i.xlarge", user_gb_to_mb(16), gb_to_mb(8))
    M7I_2XLARGE = ("m7i.2xlarge", user_gb_to_mb(32), gb_to_mb(16))
    M7I_4XLARGE = ("m7i.4xlarge", user_gb_to_mb(64), gb_to_mb(32))
    M7I_8XLARGE = ("m7i.8xlarge", user_gb_to_mb(128), gb_to_mb(64))
    M7I_16XLARGE = ("m7i.16xlarge", user_gb_to_mb(256), gb_to_mb(128))

    def instance_str(self) -> str:
        return self.value[0]

    def __str__(self) -> str:
        return self.instance_str()

    def soft_mem_limit_in_mib(self) -> int:
        return self.value[1]

    def shm_in_mib(self) -> int:
        return self.value[2]

    @staticmethod
    def from_str(s: str) -> "SolverEc2Instance":
        s = s.lower()
        for ec2 in SolverEc2Instance:
            if s == ec2.instance_str():
                return ec2
        raise ValueError(f"No matching EC2Instance found for string {s}")
