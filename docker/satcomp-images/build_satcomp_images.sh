# /bin/sh
docker build -f satcomp-common/Dockerfile -t satcomp-infrastructure:common .
docker build -f satcomp-leader/Dockerfile -t satcomp-infrastructure:leader .
docker build -f satcomp-worker/Dockerfile -t satcomp-infrastructure:worker .
