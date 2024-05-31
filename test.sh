mkdir -p output
docker build -t rh_storage_collect .
docker run -v $(pwd)/output:/pure-tools/output -it rh_storage_collect