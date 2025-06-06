#!/bin/bash
# Restart the lava-slave container without rerun docker compose
# container_id: hash id of lava-slave container to restart
# lava_path: lava source code path in lava-slave container
container_id=$1
lava_path=$2
lava_version="2024.09"
script="""
cd ${lava_path} && \
python3 setup.py build -b /tmp/build egg_info --egg-base /tmp/build install --root / --no-compile --install-layout=deb lava-common && \
    rm -rf /tmp/build && \
    python3 setup.py build -b /tmp/build egg_info --egg-base /tmp/build install --root / --no-compile --install-layout=deb lava-dispatcher && \
    rm -rf /tmp/build && \
    echo "${lava_version}" > /usr/lib/python3/dist-packages/lava_common/VERSION
"""
docker exec ${container_id} bash -c "${script}"

docker restart ${container_id}
