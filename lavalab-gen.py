#!/usr/bin/env python3
#
from __future__ import print_function
import os, sys, time
import subprocess
import yaml
import re
import string
import socket
import shutil

# Defaults
boards_yaml = "boards.yaml"
tokens_yaml = "tokens.yaml"
baud_default = 115200
ser2net_port_start = 63001
ser2net_ports = {}
allowed_hosts_list = [ '"127.0.0.1","localhost"' ]

#no comment it is volontary
template_device = string.Template("""{% extends '${devicetype}.jinja2' %}
""")

template_device_connection_command = string.Template("""#
{% set connection_command = '${connection_command}' %}
""")
template_device_pdu_generic = string.Template("""
{% set hard_reset_command = '${hard_reset_command}' %}
{% set power_off_command = '${power_off_command}' %}
{% set power_on_command = '${power_on_command}' %}
""")

template_device_ser2net = string.Template("""
{% set connection_command = 'telnet ${telnet_host} ${port}' %}
""")

ser2net_dict = {}

template_settings_conf = string.Template("""
{
    "DEBUG": false,
    "STATICFILES_DIRS": [
        ["lava-server", "/usr/share/pyshared/lava_server/htdocs/"]
    ],
    "MEDIA_ROOT": "/var/lib/lava-server/default/media",
    "ARCHIVE_ROOT": "/var/lib/lava-server/default/archive",
    "STATIC_ROOT": "/usr/share/lava-server/static",
    "STATIC_URL": "/static/",
    "MOUNT_POINT": "/",
    "HTTPS_XML_RPC": false,
    "LOGIN_URL": "/accounts/login/",
    "LOGIN_REDIRECT_URL": "/",
    "ALLOWED_HOSTS": [ $allowed_hosts ],
    "CSRF_TRUSTED_ORIGINS": ["$lava_http_fqdn"],
    "CSRF_COOKIE_SECURE": $cookie_secure,
    "SESSION_COOKIE_SECURE": $session_cookie_secure,
    "SERVER_EMAIL": "$server_email",
    "EMAIL_HOST": "$email_host",
    "EMAIL_HOST_USER": "$email_host_user",
    "EMAIL_HOST_PASSWORD": "$email_host_password",
    "EMAIL_PORT": $email_port,
    "EMAIL_USE_TLS": $email_use_tls,
    "EMAIL_USE_SSL": $email_use_ssl,
    "EMAIL_BACKEND": "$email_backend",
    "EVENT_TOPIC": "$event_notification_topic",
    "INTERNAL_EVENT_SOCKET": "ipc:///tmp/lava.events",
    "EVENT_SOCKET": "tcp://*:$event_notification_port",
    "EVENT_NOTIFICATION": $event_notification_enabled,
    "EVENT_ADDITIONAL_SOCKETS": []
}
""")

template_lava_coordinator_conf = string.Template("""
{
    "port": 3079,
    "blocksize": 4096,
    "poll_delay": 3,
    "coordinator_hostname": "$masterurl"
}
""")

def dockcomp_add_device(dockcomp, worker_name, devicemap):
    if "devices" in dockcomp["services"][worker_name]:
        dc_devices = dockcomp["services"][worker_name]["devices"]
    else:
        dockcomp["services"][worker_name]["devices"] = []
        dc_devices = dockcomp["services"][worker_name]["devices"]
    for dmap in dc_devices:
        if dmap == devicemap:
            return
    dc_devices.append(devicemap)

def dockcomp_add_cap(dockcomp, worker_name, cap):
    if "cap_add" not in dockcomp["services"][worker_name]:
            dockcomp["services"][worker_name]["cap_add"] = []
    dockcomp["services"][worker_name]["cap_add"].append(cap)

def usage():
    print("%s [boardsfile.yaml]" % sys.argv[0])

def main():
    fp = open(boards_yaml, "r")
    workers = yaml.safe_load(fp)
    fp.close()

    os.mkdir("output")

    if "masters" not in workers:
        masters = {}
    else:
        masters = workers["masters"]
    for master in masters:
        keywords_master = [
            "allowed_hosts",
            "build_args",
            "event_notifications",
            "groups", "gunicorn_workers",
            "healthcheck_url", "host", "http_fqdn",
            "listen_address",
            "loglevel", "lava-coordinator",
            "name",
            "persistent_db", "pg_lava_password",
            "slaveenv", "smtp",
            "tokens", "type",
            "users",
            "version",
            "webadmin_https", "webinterface_port",
            ]
        for keyword in master:
            if not keyword in keywords_master:
                print("WARNING: unknown keyword %s" % keyword)
        name = master["name"].lower()
        print("Handle %s\n" % name)
        if not "host" in master:
            host = "local"
        else:
            host = master["host"]
        workerdir = "output/%s/%s" % (host, name)
        os.mkdir("output/%s" % host)
        shutil.copy("deploy.sh", "output/%s/" % host)
        if not "webinterface_port" in master:
            webinterface_port = "10080"
        else:
            webinterface_port = master["webinterface_port"]
        if "listen_address" in master:
            listen_address = master["listen_address"]
        else:
            listen_address = '0.0.0.0'
        dockcomp = {}
        dockcomp["version"] = "2.4"
        dockcomp["services"] = {}
        dockcomposeymlpath = "output/%s/docker-compose.yml" % host
        dockcomp["services"][name] = {}
        dockcomp["services"][name]["hostname"] = name
        dockcomp["services"][name]["ports"] = [ listen_address + ":" + str(webinterface_port) + ":80"]
        dockcomp["services"][name]["volumes"] = [ "/boot:/boot", "/lib/modules:/lib/modules" ]
        dockcomp["services"][name]["build"] = {}
        dockcomp["services"][name]["build"]["context"] = name
        if "build_args" in master:
            dockcomp["services"][name]["build"]["args"] = master['build_args']
        persistent_db = False
        if "persistent_db" in master:
            persistent_db = master["persistent_db"]
        if persistent_db:
            pg_volume_name = "pgdata_" + name
            dockcomp["services"][name]["volumes"].append(pg_volume_name + ":/var/lib/postgresql")
            etc_volume_name = "lava_etc_" + name
            dockcomp["services"][name]["volumes"].append(etc_volume_name + ":/etc/lava-server/")
            dockcomp["services"][name]["volumes"].append("lava_job_output:/var/lib/lava-server/default/media/job-output/")
            dockcomp["volumes"] = {}
            dockcomp["volumes"][etc_volume_name] = {}
            dockcomp["volumes"][pg_volume_name] = {}
            dockcomp["volumes"]["lava_job_output"] = {}

        shutil.copytree("lava-master", workerdir)
        os.mkdir("%s/devices" % workerdir)
        # handle users / tokens
        userdir = "%s/users" % workerdir
        os.mkdir(userdir)
        groupdir = "%s/groups" % workerdir
        os.mkdir(groupdir)
        worker = master
        if "pg_lava_password" in master:
            f_pg = open("%s/pg_lava_password" % workerdir, 'w')
            f_pg.write(master["pg_lava_password"])
            f_pg.close()
        else:
            f_pg = open("%s/pg_lava_password" % workerdir, 'w')
            f_pg.close()
        if "version" in worker:
            dockerfile = open("%s/Dockerfile" % workerdir, "r+")
            dockerfilec = re.sub('(^FROM.*:).*', '\g<1>%s' % worker["version"], dockerfile.read())
            dockerfile.seek(0)
            dockerfile.write(dockerfilec)
            dockerfile.close()
            dockcomp["services"][name]["image"] = "%s:%s" % (name, worker["version"])
        if "lava-coordinator" in master and master["lava-coordinator"]:
            dockcomp["services"][name]["ports"].append('3079:3079')
            f_entrypoint = open("%s/entrypoint.d/02_lava-coordinator.sh" % workerdir, 'w')
            f_entrypoint.write("#!/bin/sh\n")
            f_entrypoint.write("echo 'Start lava-coordinator'\n")
            f_entrypoint.write("mkdir /run/lava-coordinator && chown lavaserver /run/lava-coordinator\n")
            f_entrypoint.write("start-stop-daemon --start --chuid lavaserver --background --exec /usr/bin/lava-coordinator -- --logfile=/var/log/lava-server/lava-coordinator.log\n")
            f_entrypoint.write("exit $?\n")
            f_entrypoint.close()
            os.chmod("%s/entrypoint.d/02_lava-coordinator.sh" % workerdir, 0o755)
        if "gunicorn_workers" in worker:
            dockcomp["services"][name]["environment"] = {}
            dockcomp["services"][name]["environment"]["GUNICORN_WORKERS"] = worker["gunicorn_workers"]

        with open(dockcomposeymlpath, 'w') as f:
            yaml.dump(dockcomp, f)
        if "healthcheck_url" in master:
            f_hc = open("%s/health-checks/healthcheck_url" % workerdir, 'w')
            f_hc.write(master["healthcheck_url"])
            f_hc.close()
        webadmin_https = False
        if "webadmin_https" in worker:
            webadmin_https = worker["webadmin_https"]
        if webadmin_https:
            cookie_secure = "true"
            session_cookie_secure = "true"
        else:
            cookie_secure = "false"
            session_cookie_secure = "false"
        if "http_fqdn" in worker:
            lava_http_fqdn = worker["http_fqdn"]
            allowed_hosts_list.append('"%s"' % lava_http_fqdn)
        else:
            lava_http_fqdn = "127.0.0.1"
        allowed_hosts_list.append('"%s"' % name)
        if "allowed_hosts" in worker:
            for allow_host in worker["allowed_hosts"]:
                allowed_hosts_list.append('"%s"' % allow_host)
        allowed_hosts = ','.join(allowed_hosts_list)
        f_fqdn = open("%s/lava_http_fqdn" % workerdir, 'w')
        f_fqdn.write(lava_http_fqdn)
        f_fqdn.close()
        # DJANGO defaults
        email_host = "localhost"
        email_host_user = ""
        email_host_password = ""
        email_port = 25
        email_use_tls = 'false'
        email_use_ssl = 'false'
        email_backend = 'django.core.mail.backends.smtp.EmailBackend'
        server_email = "root@localhost"
        if "smtp" in worker:
            if "server_email" in worker["smtp"]:
                server_email = worker["smtp"]["server_email"]
            if "email_host" in worker["smtp"]:
                email_host = worker["smtp"]["email_host"]
            if "email_host_user" in worker["smtp"]:
                email_host_user = worker["smtp"]["email_host_user"]
            if "email_host_password" in worker["smtp"]:
                email_host_password = worker["smtp"]["email_host_password"]
            if "email_port" in worker["smtp"]:
                email_port = worker["smtp"]["email_port"]
            # django does not like True or False but want true/false (no upper case)
            if "email_use_tls" in worker["smtp"]:
                email_use_tls = worker["smtp"]["email_use_tls"]
                if isinstance(email_use_tls, bool):
                    if email_use_tls:
                        email_use_tls = 'true'
                    else:
                        email_use_tls = 'false'
            if "email_use_ssl" in worker["smtp"]:
                email_use_ssl = worker["smtp"]["email_use_ssl"]
                if isinstance(email_use_ssl, bool):
                    if email_use_ssl:
                        email_use_ssl = 'true'
                    else:
                        email_use_ssl = 'false'
            if "email_backend" in worker["smtp"]:
                email_backend = worker["smtp"]["email_backend"]
        # Event notifications
        event_notification_topic=name
        event_notification_port='5500'
        event_notification_enabled='false'
        if "event_notifications" in worker:
            if "event_notification_topic" in worker["event_notifications"]:
                event_notification_topic = worker["event_notifications"]["event_notification_topic"]
            if "event_notification_port" in worker["event_notifications"]:
                event_notification_port = worker["event_notifications"]["event_notification_port"]
            if "event_notification_enabled" in worker["event_notifications"]:
                event_notification_enabled = worker["event_notifications"]["event_notification_enabled"]
                # django does not like True or False but want true/false (no upper case)
                if isinstance(event_notification_enabled, bool):
                    if event_notification_enabled:
                        event_notification_enabled = 'true'
                    else:
                        event_notification_enabled = 'false'
        # Substitute variables in settings.conf
        fsettings = open("%s/settings.conf" % workerdir, 'w')
        fsettings.write(
            template_settings_conf.substitute(
                cookie_secure=cookie_secure,
                session_cookie_secure=session_cookie_secure,
                lava_http_fqdn=lava_http_fqdn,
                allowed_hosts=allowed_hosts,
                email_host = email_host,
                email_host_user = email_host_user,
                email_host_password = email_host_password,
                email_port = email_port,
                email_use_tls = email_use_tls,
                email_use_ssl = email_use_ssl,
                email_backend = email_backend,
                server_email = server_email,
                event_notification_topic = event_notification_topic,
                event_notification_port = event_notification_port,
                event_notification_enabled = event_notification_enabled
                )
            )
        fsettings.close()
        if "users" in worker:
            for user in worker["users"]:
                keywords_users = [ "name", "staff", "superuser", "password", "token", "email", "groups" ]
                for keyword in user:
                    if not keyword in keywords_users:
                        print("WARNING: unknown keyword %s" % keyword)
                username = user["name"]
                ftok = open("%s/%s" % (userdir, username), "w")
                if "token" in user:
                    token = user["token"]
                    ftok.write("TOKEN=" + token + "\n")
                if "password" in user:
                    password = user["password"]
                    ftok.write("PASSWORD=" + password + "\n")
                    # libyaml convert yes/no to true/false...
                if "email" in user:
                    email = user["email"]
                    ftok.write("EMAIL=" + email + "\n")
                if "staff" in user:
                    value = user["staff"]
                    if value is True:
                        ftok.write("STAFF=1\n")
                if "superuser" in user:
                    value = user["superuser"]
                    if value is True:
                        ftok.write("SUPERUSER=1\n")
                ftok.close()
                if "groups" in user:
                    for group in user["groups"]:
                        groupname = group["name"]
                        print("\tAdd user %s to %s" % (username, groupname))
                        fgrp_userlist = open("%s/%s.group.list" % (groupdir, groupname), "a")
                        fgrp_userlist.write("%s\n" % username)
                        fgrp_userlist.close()
        if "groups" in worker:
            for group in worker["groups"]:
                groupname = group["name"]
                print("\tAdding group %s" % groupname)
                fgrp = open("%s/%s.group" % (groupdir, groupname), "w")
                fgrp.write("GROUPNAME=%s\n" % groupname)
                submitter = False
                if "submitter" in group:
                    submitter = group["submitter"]
                if submitter:
                    fgrp.write("SUBMIT=1\n")
                fgrp.close()
        tokendir = "%s/tokens" % workerdir
        os.mkdir(tokendir)
        if "tokens" in worker:
            filename_num = {}
            print("Found tokens")
            for token in worker["tokens"]:
                keywords_tokens = [ "username", "token", "description" ]
                for keyword in token:
                    if not keyword in keywords_tokens:
                        print("WARNING: unknown keyword %s" % keyword)
                username = token["username"]
                description = token["description"]
                if username in filename_num:
                    number = filename_num[username]
                    filename_num[username] = filename_num[username] + 1
                else:
                    filename_num[username] = 1
                    number = 0
                filename = "%s-%d" % (username, number)
                print("\tAdd token for %s in %s" % (username, filename))
                ftok = open("%s/%s" % (tokendir, filename), "w")
                ftok.write("USER=" + username + "\n")
                vtoken = token["token"]
                ftok.write("TOKEN=" + vtoken + "\n")
                ftok.write("DESCRIPTION=\"%s\"" % description)
                ftok.close()
        if "slaveenv" in worker:
            for slaveenv in worker["slaveenv"]:
                slavename = slaveenv["name"]
                envdir = "%s/env/%s" % (workerdir, slavename)
                if not os.path.isdir(envdir):
                    os.mkdir(envdir)
                fenv = open("%s/env.yaml" % envdir, 'w')
                fenv.write("overrides:\n")
                for line in slaveenv["env"]:
                    fenv.write("  %s\n" % line)
                fenv.close()
        if "loglevel" in worker:
            for component in worker["loglevel"]:
                if component != "lava-master" and component != "lava-logs" and component != 'lava-server-gunicorn' and component != "lava-scheduler":
                    print("ERROR: invalid loglevel component %s" % component)
                    sys.exit(1)
                loglevel = worker["loglevel"][component]
                if loglevel != 'DEBUG' and loglevel != 'INFO' and loglevel != 'WARN' and loglevel != 'ERROR':
                    print("ERROR: invalid loglevel %s for %s" % (loglevel, component))
                    sys.exit(1)
                fcomponent = open("%s/default/%s" % (workerdir, component), 'w')
                fcomponent.write("LOGLEVEL=%s\n" % loglevel)
                fcomponent.close()

    default_slave = "lab-slave-0"
    if "slaves" not in workers:
        slaves = {}
    else:
        slaves = workers["slaves"]
    for slave in slaves:
        keywords_slaves = [
            "arch",
            "bind_dev", "build_args",
            "custom_volumes",
            "devices", "dispatcher_ip", "default_slave",
            "extra_actions", "export_ser2net", "expose_ser2net", "expose_ports", "env",
            "host", "host_healthcheck",
            "loglevel", "lava-coordinator", "lava_worker_token",
            "name",
            "remote_user", "remote_master", "remote_address", "remote_rpc_port", "remote_proto", "remote_user_token",
            "tags",
            "use_docker", "use_nfs", "use_nbd", "use_overlay_server", "use_tftp", "use_tap",
            "version",
        ]
        for keyword in slave:
            if not keyword in keywords_slaves:
                print("WARNING: unknown keyword %s" % keyword)
        name = slave["name"].lower()
        if len(slaves) == 1:
            default_slave = name
        print("Handle %s" % name)
        if not "host" in slave:
            host = "local"
        else:
            host = slave["host"]
        if slave.get("default_slave") and slave["default_slave"]:
             default_slave = name
        workerdir = "output/%s/%s" % (host, name)
        dockcomposeymlpath = "output/%s/docker-compose.yml" % host
        if not os.path.isdir("output/%s" % host):
            os.mkdir("output/%s" % host)
            shutil.copy("deploy.sh", "output/%s/" % host)
            dockcomp = {}
            dockcomp["version"] = "2.0"
            dockcomp["services"] = {}
        else:
            #master exists
            fp = open(dockcomposeymlpath, "r")
            dockcomp = yaml.safe_load(fp)
            fp.close()
        dockcomp["services"][name] = {}
        dockcomp["services"][name]["hostname"] = name
        dockcomp["services"][name]["dns_search"] = ""
        dockcomp["services"][name]["ports"] = []
        dockcomp["services"][name]["volumes"] = [ "/boot:/boot", "/lib/modules:/lib/modules" ]
        dockcomp["services"][name]["environment"] = {}
        dockcomp["services"][name]["build"] = {}
        dockcomp["services"][name]["build"]["context"] = name
        dockcomp["services"][name]["privileged"] = True
        if "build_args" in slave:
            dockcomp["services"][name]["build"]["args"] = slave['build_args']
        # insert here remote

        shutil.copytree("lava-slave", workerdir)
        fp = open("%s/phyhostname" % workerdir, "w")
        fp.write(host)
        fp.close()

        worker = slave
        worker_name = name
        slave_master = None
        if "version" in worker:
            dockerfile = open("%s/Dockerfile" % workerdir, "r+")
            dockerfilec = re.sub('(^FROM.*:).*', '\g<1>%s' % worker["version"], dockerfile.read())
            dockerfile.seek(0)
            dockerfile.write(dockerfilec)
            dockerfile.close()
            dockcomp["services"][name]["image"] = "%s:%s" % (name, worker["version"])
        if "arch" in worker:
            if worker["arch"] == 'arm64':
                dockerfile = open("%s/Dockerfile" % workerdir, "r+")
                dockerfilec = dockerfile.read().replace("lava-slave-base", "lava-slave-base-arm64")
                dockerfile.seek(0)
                dockerfile.write(dockerfilec)
                dockerfile.close()
        #NOTE remote_master is on slave
        if not "remote_master" in worker:
            remote_master = "lava-master"
        else:
            remote_master = worker["remote_master"]
        if not "remote_address" in worker:
            remote_address = remote_master
        else:
            remote_address = worker["remote_address"]
        if not "remote_rpc_port" in worker:
            remote_rpc_port = "80"
        else:
            remote_rpc_port = worker["remote_rpc_port"]
        dockcomp["services"][worker_name]["environment"]["LAVA_MASTER"] = remote_address
        if "lava_worker_token" in worker:
            fsetupenv = open("%s/setupenv" % workerdir, "a")
            fsetupenv.write("LAVA_WORKER_TOKEN=%s\n" % worker["lava_worker_token"])
            fsetupenv.close()
        remote_user = worker["remote_user"]
        # find master
        remote_token = "BAD"
        if "masters" in workers:
            masters = workers["masters"]
        else:
            masters = {}
            if "remote_user_token" in worker:
                remote_token = worker["remote_user_token"]
        for fm in masters:
            if fm["name"].lower() == remote_master.lower():
                slave_master = fm
                for fuser in fm["users"]:
                    if fuser["name"] == remote_user:
                        remote_token = fuser["token"]
        if remote_token == "BAD":
            print("Cannot find %s on %s" % (remote_user, remote_master))
            sys.exit(1)
        if "env" in slave:
            if not slave_master:
                print("Cannot set env without master")
                sys.exit(1)
            envdir = "output/%s/%s/env/%s" % (slave_master["host"], slave_master["name"], name)
            os.mkdir(envdir)
            fenv = open("%s/env.yaml" % envdir, 'w')
            fenv.write("overrides:\n")
            for line in slave["env"]:
                fenv.write("  %s\n" % line)
            fenv.close()
        if "custom_volumes" in slave:
            for cvolume in slave["custom_volumes"]:
                dockcomp["services"][worker_name]["volumes"].append(cvolume)
                volume_name = cvolume.split(':')[0]
                if "volumes" not in dockcomp:
                    dockcomp["volumes"] = {}
                if cvolume[0] != '/':
                    dockcomp["volumes"][volume_name] = {}
        if not "remote_proto" in worker:
            remote_proto = "http"
        else:
            remote_proto = worker["remote_proto"]
        remote_uri = "%s://%s:%s@%s:%s/RPC2" % (remote_proto, remote_user, remote_token, remote_address, remote_rpc_port)
        remote_master_url = "%s://%s:%s" % (remote_proto, remote_address, remote_rpc_port)

        fsetupenv = open("%s/setupenv" % workerdir, "a")
        fsetupenv.write("LAVA_MASTER_URI=%s\n" % remote_uri)
        fsetupenv.write("LAVA_MASTER_URL=%s\n" % remote_master_url)
        fsetupenv.write("LAVA_MASTER_USER=%s\n" % remote_user)
        fsetupenv.write("LAVA_MASTER_BASEURI=%s://%s:%s/RPC2\n" % (remote_proto, remote_address, remote_rpc_port))
        fsetupenv.write("LAVA_MASTER_TOKEN=%s\n" % remote_token)
        fsetupenv.close()

        if "lava-coordinator" in worker and worker["lava-coordinator"]:
            fcoordinator = open("%s/lava-coordinator/lava-coordinator.cnf" % workerdir, 'w')
            fcoordinator.write(template_lava_coordinator_conf.substitute(masterurl=remote_address))
            fcoordinator.close()
        if "dispatcher_ip" in worker:
            dockcomp["services"][worker_name]["environment"]["LAVA_DISPATCHER_IP"] = worker["dispatcher_ip"]
        if "expose_ports" in worker:
            for eports in worker["expose_ports"]:
                dockcomp["services"][name]["ports"].append("%s" % eports)
        if "bind_dev" in worker and worker["bind_dev"]:
            dockcomp["services"][worker_name]["volumes"].append("/dev:/dev")
            dockcomp["services"][worker_name]["privileged"] = True
        if "use_tap" in worker and worker["use_tap"]:
            dockcomp_add_device(dockcomp, worker_name, "/dev/net/tun:/dev/net/tun")
            dockcomp_add_cap(dockcomp, worker_name, "NET_ADMIN")
        if "host_healthcheck" in worker and worker["host_healthcheck"]:
            dockcomp["services"]["healthcheck"] = {}
            dockcomp["services"]["healthcheck"]["ports"] = ["8080:8080"]
            dockcomp["services"]["healthcheck"]["build"] = {}
            dockcomp["services"]["healthcheck"]["build"]["context"] = "healthcheck"
            if remote_master in worker and "build_args" in worker[remote_master]:
                dockcomp["services"]["healthcheck"]["build"]["args"] = worker[remote_master]['build_args']
            shutil.copytree("healthcheck", "output/%s/healthcheck" % host)
        if "extra_actions" in worker:
            fp = open("%s/scripts/extra_actions" % workerdir, "w")
            for eaction in worker["extra_actions"]:
                fp.write(eaction)
                fp.write("\n")
            fp.close()
            os.chmod("%s/scripts/extra_actions" % workerdir, 0o755)

        if "devices" in worker:
            if not os.path.isdir("output/%s/udev" % host):
                os.mkdir("output/%s/udev" % host)
            for udev_dev in worker["devices"]:
                udev_line = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="%04x", ATTRS{idProduct}=="%04x",' % (udev_dev["idvendor"], udev_dev["idproduct"])
                if "serial" in udev_dev:
                    udev_line += 'ATTRS{serial}=="%s", ' % udev_dev["serial"]
                if "devpath" in udev_dev:
                    udev_line += 'ATTRS{devpath}=="%s", ' % udev_dev["devpath"]
                udev_line += 'MODE="0664", OWNER="uucp", SYMLINK+="%s"\n' % udev_dev["name"]
                fudev = open("output/%s/udev/99-lavaworker-udev.rules" % host, "a")
                fudev.write(udev_line)
                fudev.close()
                if not "bind_dev" in slave or not slave["bind_dev"]:
                    dockcomp_add_device(dockcomp, worker_name, "/dev/%s:/dev/%s" % (udev_dev["name"], udev_dev["name"]))
        use_tftp = True
        if "use_tftp" in worker:
            use_tftp = worker["use_tftp"]
        if use_tftp:
            if "dispatcher_ip" in worker:
                dockcomp["services"][name]["ports"].append(worker["dispatcher_ip"] + ":69:69/udp")
            else:
                dockcomp["services"][name]["ports"].append("69:69/udp")
        use_docker = False
        if "use_docker" in worker:
            use_docker = worker["use_docker"]
        if use_docker:
            dockcomp["services"][worker_name]["volumes"].append("/var/run/docker.sock:/var/run/docker.sock")
            dockcomp["services"][worker_name]["volumes"].append("/run/udev/data:/run/udev/data")
        # TODO permit to change the range of NBD ports
        use_nbd = True
        if "use_nbd" in worker:
            use_nbd = worker["use_nbd"]
        if use_nbd:
            dockcomp["services"][name]["ports"].append("61950-62000:61950-62000")
            fp = open("%s/scripts/extra_actions" % workerdir, "a")
            # LAVA issue 585 need to remove /etc/nbd-server/config
            fp.write("apt-get -y install nbd-server && rm -f /etc/nbd-server/config\n")
            fp.close()
            os.chmod("%s/scripts/extra_actions" % workerdir, 0o755)
        use_overlay_server = True
        if "use_overlay_server" in worker:
            use_overlay_server = worker["use_overlay_server"]
        if use_overlay_server:
            dockcomp["services"][name]["ports"].append("80:80")
        use_nfs = False
        if "use_nfs" in worker:
            use_nfs = worker["use_nfs"]
        if use_nfs or use_docker:
            dockcomp["services"][worker_name]["volumes"].append("/var/lib/lava/dispatcher/tmp:/var/lib/lava/dispatcher/tmp")
        if use_nfs:
            fp = open("%s/scripts/extra_actions" % workerdir, "a")
            # LAVA check if this package is installed when doing NFS jobs
            # So we need to install it, even if it is not used
            fp.write("apt-get -y install nfs-kernel-server\n")
            fp.close()
            os.chmod("%s/scripts/extra_actions" % workerdir, 0o755)
        with open(dockcomposeymlpath, 'w') as f:
            yaml.dump(dockcomp, f)
        if "loglevel" in worker:
            for component in worker["loglevel"]:
                if component != "lava-slave":
                    print("ERROR: invalid loglevel component %s" % component)
                    sys.exit(1)
                loglevel = worker["loglevel"][component]
                if loglevel != 'DEBUG' and loglevel != 'INFO' and loglevel != 'WARN' and loglevel != 'ERROR':
                    print("ERROR: invalid loglevel %s for %s" % (loglevel, component))
                    sys.exit(1)
                fcomponent = open("%s/default/%s" % (workerdir, component), 'w')
                fcomponent.write("LOGLEVEL=%s\n" % loglevel)
                fcomponent.close()

    if "boards" not in workers:
        boards = {}
    else:
        boards = workers["boards"]
    for board in boards:
        board_name = board["name"]
        if "slave" in board:
            worker_name = board["slave"]
        else:
            worker_name = default_slave
        print("\tFound %s on %s" % (board_name, worker_name))
        found_slave = False
        for fs in workers["slaves"]:
            if fs["name"].lower() == worker_name.lower():
                slave = fs
                found_slave = True
        if not found_slave:
            print("Cannot find slave %s" % worker_name)
            sys.exit(1)
        if not "host" in slave:
            host = "local"
        else:
            host = slave["host"]
        workerdir = "output/%s/%s" % (host, worker_name)
        dockcomposeymlpath = "output/%s/docker-compose.yml" % host
        fp = open(dockcomposeymlpath, "r")
        dockcomp = yaml.safe_load(fp)
        fp.close()
        device_path = "%s/devices/" % workerdir
        devices_path = "%s/devices/%s" % (workerdir, worker_name)
        devicetype = board["type"]
        device_line = template_device.substitute(devicetype=devicetype)
        if "pdu_generic" in board:
            hard_reset_command = board["pdu_generic"]["hard_reset_command"]
            power_off_command = board["pdu_generic"]["power_off_command"]
            power_on_command = board["pdu_generic"]["power_on_command"]
            device_line += template_device_pdu_generic.substitute(hard_reset_command=hard_reset_command, power_off_command=power_off_command, power_on_command=power_on_command)
        use_kvm = False
        if "kvm" in board:
            use_kvm = board["kvm"]
        if use_kvm:
            dockcomp_add_device(dockcomp, worker_name, "/dev/kvm:/dev/kvm")
            # board specific hacks
        if devicetype == "qemu" and not use_kvm:
            device_line += "{% set no_kvm = True %}\n"
        if "uart" in board:
            keywords_uart = [ "baud", "devpath", "idproduct", "idvendor", "interfacenum", "serial", "use_ser2net", "worker" ]
            for keyword in board["uart"]:
                if not keyword in keywords_uart:
                    print("WARNING: unknown keyword %s" % keyword)
            uart = board["uart"]
            baud = board["uart"].get("baud", baud_default)
            idvendor = board["uart"]["idvendor"]
            idproduct = board["uart"]["idproduct"]
            if type(idproduct) == str:
                print("Please put hexadecimal IDs for product %s (like 0x%s)" % (board_name, idproduct))
                sys.exit(1)
            if type(idvendor) == str:
                print("Please put hexadecimal IDs for vendor %s (like 0x%s)" % (board_name, idvendor))
                sys.exit(1)
            udev_line = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="%04x", ATTRS{idProduct}=="%04x",' % (idvendor, idproduct)
            if "serial" in uart:
                udev_line += 'ATTRS{serial}=="%s", ' % board["uart"]["serial"]
            if "devpath" in uart:
                udev_line += 'ATTRS{devpath}=="%s", ' % board["uart"]["devpath"]
            if "interfacenum" in uart:
                udev_line += 'ENV{ID_USB_INTERFACE_NUM}=="%s", ' % board["uart"]["interfacenum"]
            udev_line += 'MODE="0664", OWNER="uucp", SYMLINK+="%s"\n' % board_name
            if not os.path.isdir("output/%s/udev" % host):
                os.mkdir("output/%s/udev" % host)
            fp = open("output/%s/udev/99-lavaworker-udev.rules" % host, "a")
            fp.write(udev_line)
            fp.close()
            if not "bind_dev" in slave or not slave["bind_dev"]:
                dockcomp_add_device(dockcomp, worker_name, "/dev/%s:/dev/%s" % (board_name, board_name))
            use_ser2net = False
            ser2net_keepopen = False
            if "use_ser2net" in uart:
                use_ser2net = uart["use_ser2net"]
            if "ser2net_keepopen" in uart:
                ser2net_keepopen = uart["ser2net_keepopen"]
            if not use_ser2net and not "connection_command" in board:
                use_ser2net = True
            if use_ser2net:
                if "worker" in uart:
                    worker_ser2net = uart["worker"]
                    telnet_host = worker_ser2net
                else:
                    worker_ser2net = worker_name
                    telnet_host = "127.0.0.1"
                ser2netdir = "output/%s/%s" % (host, worker_ser2net)
                if not os.path.isdir(ser2netdir):
                    os.mkdir(ser2netdir)
                if (not "bind_dev" in slave or not slave["bind_dev"]) and worker_ser2net == worker_name:
                    dockcomp_add_device(dockcomp, worker_name, "/dev/%s:/dev/%s" % (board_name, board_name))
                udev_line = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="%04x", ATTRS{idProduct}=="%04x",' % (idvendor, idproduct)
                if "serial" in uart:
                    udev_line += 'ATTRS{serial}=="%s", ' % board["uart"]["serial"]
                if "devpath" in uart:
                    udev_line += 'ATTRS{devpath}=="%s", ' % board["uart"]["devpath"]
                if "interfacenum" in uart:
                    udev_line += 'ENV{ID_USB_INTERFACE_NUM}=="%s", ' % board["uart"]["interfacenum"]
                udev_line += 'MODE="0664", OWNER="uucp", SYMLINK+="%s"\n' % board_name
                udevdir = "output/%s/%s/udev" % (host, worker_ser2net)
                if not os.path.isdir(udevdir):
                    os.mkdir(udevdir)
                fp = open("%s/99-lavaworker-udev.rules" % udevdir, "a")
                fp.write(udev_line)
                fp.close()
                if not worker_ser2net in ser2net_ports:
                    ser2net_ports[worker_ser2net] = ser2net_port_start
                    fp = open("%s/ser2net.yaml" % ser2netdir, "a")
                    fp.write("%YAML 1.1\n---\n")
                    fp.close()
                device_line += template_device_ser2net.substitute(port=ser2net_ports[worker_ser2net], telnet_host=telnet_host)
                # YAML version
                fp = open("%s/ser2net.yaml" % ser2netdir, "a")
                fp.write("connection: &con%d\n" % ser2net_ports[worker_ser2net])
                fp.write("  accepter: telnet(rfc2217),tcp,%d\n" % ser2net_ports[worker_ser2net])
                fp.write("  enable: on\n")
                if ser2net_keepopen:
                    ser2net_yaml_line= "  connector: keepopen(retry-time=2000,discard-badwrites),serialdev,/dev/%s,%dn81,local" % (board_name, baud)
                else:
                    ser2net_yaml_line = "  connector: serialdev,/dev/%s,%dn81,local" % (board_name, baud)
                if "ser2net_options" in uart:
                    for ser2net_yaml_option in uart["ser2net_options"]:
                        ser2net_yaml_line += ",%s" % ser2net_yaml_option
                ser2net_yaml_line += "\n"
                fp.write(ser2net_yaml_line)
                fp.write("  options:\n")
                fp.write("    max-connections: 10\n")
                ser2net_ports[worker_ser2net] += 1
                fp.close()
        if "connection_command" in board:
            connection_command = board["connection_command"]
            device_line += template_device_connection_command.substitute(connection_command=connection_command)
        if "uboot_ipaddr" in board:
            device_line += "{%% set uboot_ipaddr_cmd = 'setenv ipaddr %s' %%}\n" % board["uboot_ipaddr"]
        if "uboot_macaddr" in board:
            device_line += '{% set uboot_set_mac = true %}'
            device_line += "{%% set uboot_mac_addr = '%s' %%}\n" % board["uboot_macaddr"]
        if "fastboot_serial_number" in board:
            fserial = board["fastboot_serial_number"]
            device_line += "{%% set fastboot_serial_number = '%s' %%}" % fserial
        if "tags" in board:
            tagdir = "%s/tags/" % workerdir
            ftag = open("%s/%s" % (tagdir, board_name), 'w')
            for tag in board["tags"]:
                ftag.write("%s\n" % tag)
            ftag.close()
        if "tags" in slave:
            tagdir = "%s/tags/" % workerdir
            ftag = open("%s/%s" % (tagdir, board_name), 'a')
            for tag in slave["tags"]:
                ftag.write("%s\n" % tag)
            ftag.close()
        if "aliases" in board:
            aliases_dir = "%s/aliases/" % workerdir
            falias = open("%s/%s" % (aliases_dir, board["type"]), 'a')
            for alias in board["aliases"]:
                falias.write("%s\n" % alias)
            falias.close()
        if "user" in board:
            deviceinfo = open("%s/deviceinfo/%s" % (workerdir, board_name), 'w')
            deviceinfo.write("DEVICE_USER=%s\n" % board["user"])
            deviceinfo.close()
        if "group" in board:
            if "user" in board:
                    print("user and group are exclusive")
                    sys.exit(1)
            deviceinfo = open("%s/deviceinfo/%s" % (workerdir, board_name), 'w')
            deviceinfo.write("DEVICE_GROUP=%s\n" % board["group"])
            deviceinfo.close()
        if "custom_option" in board:
            if type(board["custom_option"]) == list:
                for coption in board["custom_option"]:
                    device_line += "{%% %s %%}\n" % coption
            else:
                for line in board["custom_option"].splitlines():
                    device_line += "{%% %s %%}\n" % line
        if "raw_custom_option" in board:
            for coption in board["raw_custom_option"]:
                device_line += "%s\n" % coption
        if not os.path.isdir(device_path):
            os.mkdir(device_path)
        if not os.path.isdir(devices_path):
            os.mkdir(devices_path)
        board_device_file = "%s/%s.jinja2" % (devices_path, board_name)
        fp = open(board_device_file, "w")
        fp.write(device_line)
        fp.close()
        with open(dockcomposeymlpath, 'w') as f:
            yaml.dump(dockcomp, f)
        #end for board

    for slave_name in ser2net_ports:
        expose_ser2net = False
        for fs in workers["slaves"]:
            if fs["name"] == slave_name:
                if not "host" in fs:
                    host = "local"
                else:
                    host = fs["host"]
                if "expose_ser2net" in fs:
                    expose_ser2net = fs["expose_ser2net"]
                if "export_ser2net" in fs:
                    print("export_ser2net is deprecated, please use expose_ser2net")
                    expose_ser2net = fs["export_ser2net"]
        if not expose_ser2net:
            continue
        print("Add ser2net ports for %s (%s) %s-%s" % (slave_name, host, ser2net_port_start, ser2net_ports[slave_name]))
        dockcomposeymlpath = "output/%s/docker-compose.yml" % host
        fp = open(dockcomposeymlpath, "r")
        dockcomp = yaml.safe_load(fp)
        fp.close()
        ser2net_port_max = ser2net_ports[slave_name] - 1
        dockcomp["services"][slave_name]["ports"].append("%s-%s:%s-%s" % (ser2net_port_start, ser2net_port_max, ser2net_port_start, ser2net_port_max))
        with open(dockcomposeymlpath, 'w') as f:
            yaml.dump(dockcomp, f)

if len(sys.argv) > 1:
    if sys.argv[1] == '-h' or sys.argv[1] == '--help':
        usage()
        sys.exit(0)
    boards_yaml = sys.argv[1]

if __name__ == "__main__":
    main()

