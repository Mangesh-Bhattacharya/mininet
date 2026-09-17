#!/bin/bash
# Container entrypoint: start Open vSwitch, then run the given command.
#
# If the host kernel provides the openvswitch module (Linux hosts,
# GitHub runners), OVS uses the fast kernel datapath. Otherwise
# (Docker Desktop on Windows/macOS, many cloud kernels) ovs-vswitchd
# runs with the userspace datapath and Mininet is told to use it.

set -e

OVS_CTL=/usr/share/openvswitch/scripts/ovs-ctl

log() { echo "[mininet] $*" >&2; }

if [ ! -w /proc/sys/net ]; then
    log "WARNING: container is not privileged; Mininet will not work."
    log "Run it with: docker run --privileged ..."
fi

mkdir -p /var/run/openvswitch /var/log/openvswitch

if ! ovs-vsctl -t 1 show > /dev/null 2>&1; then
    "$OVS_CTL" --no-ovs-vswitchd --system-id=random start > /dev/null ||
        log "WARNING: could not start ovsdb-server"
    if [ "${MININET_OVS_DATAPATH:-}" != "user" ] &&
       { [ -d /sys/module/openvswitch ] ||
         modprobe openvswitch > /dev/null 2>&1; }; then
        "$OVS_CTL" --no-ovsdb-server start > /dev/null ||
            log "WARNING: could not start ovs-vswitchd"
        export MININET_OVS_DATAPATH="${MININET_OVS_DATAPATH:-kernel}"
    else
        # No kernel module: ovs-ctl would refuse to start, so start
        # ovs-vswitchd directly for the userspace (netdev) datapath
        ovs-vswitchd --pidfile --detach --log-file > /dev/null 2>&1 ||
            log "WARNING: could not start ovs-vswitchd"
        export MININET_OVS_DATAPATH=user
    fi
fi

if [ -t 0 ] && [ -t 1 ] && [ "$#" -eq 1 ] && [ "$1" = "bash" ]; then
    cat <<EOF

  Mininet container ready (Open vSwitch datapath: ${MININET_OVS_DATAPATH:-kernel})

    mn --test pingall          quick self-test
    mn                         interactive CLI (type 'exit' to leave)
    mn-doctor                  check what works in this environment
    mn -c                      clean up after a crash

  Your current directory on the host is mounted at /workspace
  (when started with scripts/mininet-docker). 'sudo' works too.

EOF
fi

exec "$@"
