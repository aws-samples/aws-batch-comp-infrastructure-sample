# /bin/sh
cd satcomp-common-base-image
docker build -t satcomp-common-base-image .
cd ..
docker build -f satcomp-leader-image/Dockerfile -t satcomp-base:leader .
docker build -f satcomp-worker-image/Dockerfile -t satcomp-base:worker .
