FROM yyx2002/lava-dispatcher:latest
# FROM lavasoftware/lava-dispatcher:2023.10

COPY debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update

# telnet is for using ser2net
# git is necessary for checkout tests
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install telnet git ser2net patch lavacli gdb-multiarch vim net-tools

COPY configs/lava-slave /etc/lava-dispatcher/lava-slave

COPY configs/tftpd-hpa /etc/default/tftpd-hpa

COPY scripts/ /usr/local/bin/
RUN chmod a+x /usr/local/bin/*

# Caution to not use any port between the Linux dynamic port range: 32768-60999
RUN find /usr/lib/python3/dist-packages/ -iname constants.py | xargs sed -i 's,XNBD_PORT_RANGE_MIN.*,XNBD_PORT_RANGE_MIN=61950,'
RUN find /usr/lib/python3/dist-packages/ -iname constants.py | xargs sed -i 's,XNBD_PORT_RANGE_MAX.*,XNBD_PORT_RANGE_MAX=62000,'

COPY ser2net.yaml /etc

# PXE stuff
RUN if [ $(uname -m) != amd64 -a $(uname -m) != x86_64 ]; then dpkg --add-architecture amd64 && apt-get update; fi
RUN apt-get -y install grub-efi-amd64-bin:amd64
RUN if [ $(uname -m) != amd64 -a $(uname -m) != x86_64 ]; then dpkg --remove architecture amd64 && apt-get update; fi
COPY grub.cfg /root/

COPY default/* /etc/default/

COPY phyhostname /root/
COPY setupenv /root/
COPY scripts/setup.sh .

COPY lava-patch/ /root/lava-patch
RUN cd /usr/lib/python3/dist-packages && for patch in $(ls /root/lava-patch/*patch) ; do echo "APPLY $patch"; patch -p1 < $patch || exit $?;done

# needed for lavacli identities
RUN mkdir -p /root/.config

COPY devices/ /root/devices/
COPY tags/ /root/tags/
COPY aliases/ /root/aliases/
COPY deviceinfo/ /root/deviceinfo/
COPY entrypoint.d/* /root/entrypoint.d/
RUN chmod +x /root/entrypoint.d/*

RUN if [ -x /usr/local/bin/extra_actions ] ; then /usr/local/bin/extra_actions ; fi

EXPOSE 69/udp 80

RUN git config --global http.proxy http://10.161.28.28:7890
RUN git config --global https.proxy http://10.161.28.28:7890
RUN mkdir -p /root/flipgdb
COPY fliputils.py /root/flipgdb/fliputils.py
COPY extract-ikconfig /root/extract-ikconfig
RUN chmod +x /root/extract-ikconfig
COPY check-pvpanic /root/check-pvpanic
RUN chmod +x /root/check-pvpanic

CMD /usr/local/bin/start.sh
