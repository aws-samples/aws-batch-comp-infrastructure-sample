# /bin/sh
cd common
docker build -t satcomp-mallob:common .
cd ..

cd leader
docker build -t satcomp-mallob:leader .
cd ..

cd worker
docker build -t satcomp-mallob:worker .
cd ..