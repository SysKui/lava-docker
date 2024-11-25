#!/bin/sh
set -u -e
if [ "$(id -u)" -ne 0 ]; then
  echo "should be root"
  exit 1
fi
systemctl stop lava
rm -r output/
./lavalab-gen.sh
cp ./backup-20241119_1241/* ./output/lava-test-1/master/backup && cd output/lava-test-1/ && docker-compose build
systemctl start lava
