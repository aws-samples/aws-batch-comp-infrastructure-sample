# /bin/sh
cd common
docker build --no-cache -t satcomp-mallob:common .
cd ..

cd leader
docker build --no-cache -t satcomp-mallob:leader .
cd ..

cd worker
docker build --no-cache -t satcomp-mallob:worker .
cd ..
