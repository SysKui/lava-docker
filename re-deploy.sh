#!/bin/sh
set -u -e
if [ "$(id -u)" -ne 0 ]; then
  echo "should be root"
  exit 1
fi
SHELLDIR="/data/user_home/yyx/lava-docker"
$SHELLDIR/backup.sh
systemctl stop lava
rm -r $SHELLDIR/output/
$SHELLDIR/lavalab-gen.sh
cp $SHELLDIR/backup-latest/* $SHELLDIR/output/lava-test-1/master/backup && cd $SHELLDIR/output/lava-test-1/ && docker-compose build
systemctl start lava
