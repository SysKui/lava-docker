#!/bin/bash
# Restart lava-master container without rerun docker compose
# container_id: hash id of lava-master container to restart
# lava_path: lava source code path in lava-master container
container_id=$1
lava_path=$2
lava_version="2024.09"
script="""
cd ${lava_path} && \
python3 setup.py build -b /tmp/build egg_info --egg-base /tmp/build install --root /install --no-compile --install-layout=deb lava-common && \
rm -rf /tmp/build && \
python3 setup.py build -b /tmp/build egg_info --egg-base /tmp/build install --root /install --no-compile --install-layout=deb lava-coordinator && \
rm -rf /tmp/build && \
python3 setup.py build -b /tmp/build egg_info --egg-base /tmp/build install --root /install --no-compile --install-layout=deb lava-server && \
rm -rf /tmp/build && \

touch /install/var/log/lava-server/django.log && \

chown -R lavaserver:lavaserver /install/etc/lava-server/dispatcher-config/ && \
chown -R lavaserver:lavaserver /install/etc/lava-server/dispatcher.d/ && \
chown -R lavaserver:lavaserver /install/etc/lava-server/settings.d/ && \
chown -R lavaserver:lavaserver /install/var/lib/lava-server/default/ && \
chown -R lavaserver:lavaserver /install/var/lib/lava-server/home/ && \
chown -R lavaserver:adm /install/var/log/lava-server/ && \

mv /install/usr/lib/python3/dist-packages/lava_results_app/static/lava_results_app/ /install/usr/share/lava-server/static/lava_results_app && \
mv /install/usr/lib/python3/dist-packages/lava_scheduler_app/static/lava_scheduler_app/ /install/usr/share/lava-server/static/lava_scheduler_app && \
mv /install/usr/lib/python3/dist-packages/lava_server/static/lava_server/ /install/usr/share/lava-server/static/lava_server && \
ln -s /usr/lib/python3/dist-packages/django/contrib/admin/static/admin/ /install/usr/share/lava-server/static/admin && \
ln -s /usr/lib/python3/dist-packages/rest_framework/static/rest_framework/ /install/usr/share/lava-server/static/rest_framework && \
python3 -m whitenoise.compress /install/usr/share/lava-server/static/ && \
find /usr/lib/python3/dist-packages/ -name '__pycache__' -type d -exec rm -r "{}" +
echo "${lava_version}" > /install/usr/lib/python3/dist-packages/lava_common/VERSION

cp -r /install/* /
"""
docker exec ${container_id} bash -c "${script}"
sleep 2
docker restart ${container_id}
