#!/bin/bash

hostfile="$1"
problem_path="$2"
totalWorkerNodes=$3

#only works in linux
server_ip=$(/sbin/ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1)
totalNumberOfSolverInstances=$(($totalWorkerNodes*4))

#run smts server
python3 /SMTS/server/smts.py -p &

sleep 1
#run lemma server
/SMTS/build/lemma_server -s$server_ip:3000 &

#run solver clients
mpirun --mca btl_tcp_if_include eth0 --allow-run-as-root -np $totalNumberOfSolverInstances \
  --hostfile "$hostfile" --use-hwthread-cpus --map-by node:PE=4 --bind-to none --report-bindings \
  /SMTS/build/solver_opensmt -s$server_ip:3000 &

#send instance
python3 /SMTS/server/client.py 3000 "$problem_path"

wait
