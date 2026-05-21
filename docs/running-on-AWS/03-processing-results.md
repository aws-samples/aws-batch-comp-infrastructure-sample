# Processing Results

This page explains how to collect and analyze solver results.

## Collecting Results

Use the `collect` command to collect results from solver output queues:

```bash
./satcomp.py collect
```

Or combine with terminate-instances:
```bash
./satcomp.py terminate-instances collect
```

### Using a Custom Jobs File

If you used a custom jobs.yml, specify it:

```bash
./satcomp.py collect my_jobs.yml
```

## Results Directory

A results summary is saved to the directory specified in `my_jobs.yml`:

```yaml
results_dir: results
```

<!--
After processing, each entry in the `results.txt` (default name) file contains a pointer to an S3 location that contains the full results:
```
results/
  solver1/              # one directory per solver
    results.csv         # summary of all jobs for that solver
    job_1/              # individual job details, pointed to by each line in results.txt file
      input.json
      stdout.txt
      stderr.txt
      solver_out.json
  solver2/
    results.csv
    ...
```
-->

## Results Format

### results.csv

The main results file contains one row per job:


| Column | Description |
|--------|-------------|
| solver | Solver name |
| process_return_code | Process exit code |
| solver_result_code | Result value from solver |
| solving_result | SAT, UNSAT, UNKNOWN, TIMEOUT, or ERROR |
| solver_runtime_ms | Runtime in milliseconds |
| job_time_start | timestamp of job start for formula |
| formula_s3_uri | S3 URI for formula |
| upload_dir_uri | S3 location of detailed jobs logs |


### Per-Job Files

Each job's details are uploaded to S3 and can be found in:

- `input.json` - Input parameters (formula path, timeout, options)
- `stdout.txt` - Solver's standard output
- `stderr.txt` - Solver's standard error
- `solver_out.json` - Parsed result and timing information

### Download S3 results

To download all results from S3 to the local directory `s3_results`:
```bash
aws s3 sync s3://{bucket}/2026-parallel-{solver}/ ./s3_results/
```

## Analyzing Results

### Basic Analysis

Count results by type:
```bash
cat results/solver1/results.csv | cut -d, -f3 | sort | uniq -c
```

### Finding Timeouts

```bash
grep "TIMEOUT" results/*/results.csv
```

### Comparing Solvers

To compare results across solvers, you can use standard data analysis tools
(Python pandas, R, etc.) on the CSV files.

Example Python analysis:
```python
import pandas as pd

# Load results
solver1 = pd.read_csv('results/solver1/results.csv')
solver2 = pd.read_csv('results/solver2/results.csv')

# Compare SAT counts
print(f"Solver1 SAT: {len(solver1[solver1.result == 'SAT'])}")
print(f"Solver2 SAT: {len(solver2[solver2.result == 'SAT'])}")

# Find formulas solved by solver1 but not solver2
merged = solver1.merge(solver2, on='formula', suffixes=('_1', '_2'))
unique_to_1 = merged[(merged.result_1 == 'SAT') & (merged.result_2 != 'SAT')]
```

## Re-Running Failed Jobs

If some jobs failed (ERROR result), you can re-run them:

1. Identify failed formulas from results.csv
2. Create a new jobs.yml with a bucket that contains only those formulas
3. Submit again:
   ```bash
   ./satcomp.py my_reruns.yml submit
   ```

This helps in the unusual case that your jobs encountered a transient failure.

## Debugging Failed Jobs

For jobs that failed, check the logs:

1. Find the `upload_uri` from results.csv
2. Download the logs to a local directory, e.g. `debug`:
   ```bash
   aws s3 sync s3://{upload_uri}/ ./debug/
   ```
3. Examine stdout.txt and stderr.txt for error messages

Common failure causes:
- Memory exhaustion (check for OOM in stderr)
- Disk full (solver couldn't write output)
- Timeout (check if runtime_ms >= timeout)
- Solver crash (non-zero return code)

## Cleaning Up Results

To start fresh:

```bash
rm -rf results/.      # Collecting results always appends to existing files.
./satcomp.py purge    # Clear any remaining queue messages
```

## Next Steps

- [Teardown](04-teardown.md) to tear down resources
- [Troubleshooting](05-troubleshooting.md) for common issues
