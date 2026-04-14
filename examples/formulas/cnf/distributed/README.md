# Distributed Test Problem Set

Curated SAT instances for validating mallob distributed solving at 10-node and 100-node scale.

## Populating this directory

Download the benchmark files from the SAT Competition S3 bucket (ask your team for the bucket name):

```bash
aws s3 cp s3://<satcomp-bucket>/benchmarks/sat/easy/ . --recursive
```

Or selectively download the instances listed in `manifest.yml`.

For hard instances, you can also generate Ramsey formulas locally:

```bash
cd tools/ramsey-generator
gcc ramsey-generator.c -O2 -o ramsey-generator
./ramsey-generator 42 5 5 > ../../examples/formulas/cnf/distributed/ramsey_42_5_5.cnf
```

## Usage

Reference these formulas in `examples/configs/sat-distributed-mallob/jobs.yml`
or upload to S3 via `python satcomp.py submit`.

See `manifest.yml` for the full list of problems with expected results.
