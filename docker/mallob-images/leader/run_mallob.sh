#!/bin/bash

export OMPI_MCA_btl_vader_single_copy_mechanism=none
export RDMAV_FORK_SAFE=1
mpirun --mca btl_tcp_if_include eth0 --allow-run-as-root --hostfile $1 --bind-to none mallob -mono=$2 \
-zero-only-logging -sleep=1000 -t=4 -appmode=fork -nolog -v=3 -interface-fs=0 -trace-dir=competition \
-pipe-large-solutions=0 -processes-per-host=$processes_per_host -regular-process-allocation \
-max-lits-per-thread=50000000 -strict-clause-length-limit=20 -clause-filter-clear-interval=500 \
-max-lbd-partition-size=2 -export-chunks=20 -clause-buffer-discount=1.0 -satsolver=k

# mpirun --mca btl_tcp_if_include eth0 --allow-run-as-root -np 2 \
#   --hostfile $1 --use-hwthread-cpus --map-by node:PE=2 --bind-to none --report-bindings \
#   mallob -mono=$2 -satsolver="c" -cbbs=1500 -cbdf="1.0" \
#   -shufinp=0.03 -shufshcls=1 -slpp=$((50000000 * 4)) \
#   -cfhl=300 -ihlbd=8 -islbd=8 -fhlbd=8 -fslbd=8 -smcl=30 -hmcl=30 \
#   -s=1 -sleep=1000 -t=2 -appmode=thread -nolog "-v=2 -0o=1"