# Mininet in a container: runs on Linux, Windows (Docker Desktop/WSL2)
# and macOS (Docker Desktop, OrbStack, Colima) on amd64 and arm64.
#
#   docker build -t mininet .
#   docker run --rm -it --privileged mininet
#   mininet> (inside) mn --test pingall
#
# --privileged is required: Mininet creates network namespaces,
# veth pairs and Open vSwitch bridges. See docs/install/docker.md.

FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="Mininet" \
      org.opencontainers.image.description="Mininet network emulator with Open vSwitch, ready to run on any Docker host" \
      org.opencontainers.image.source="https://github.com/Mangesh-Bhattacharya/mininet" \
      org.opencontainers.image.licenses="BSD-3-Clause"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bridge-utils ca-certificates curl ethtool gcc help2man iperf iperf3 iproute2 \
        iputils-ping kmod libc6-dev make net-tools nano openvswitch-switch \
        openvswitch-testcontroller procps psmisc python3 python3-packaging \
        python3-pexpect python3-pip socat tcpdump telnet vim-tiny xterm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/mininet
COPY . .

# mininet/examples is a symlink in git, but checkouts on Windows
# (core.symlinks=false) turn it into a text file: recreate it.
# Also strip any CRLF line endings introduced by Windows checkouts.
RUN rm -rf mininet/examples && ln -s ../examples mininet/examples \
    && find bin util docker examples mininet -type f \
         \( -name '*.py' -o -name '*.sh' -o -path 'bin/*' \) \
         -exec sed -i 's/\r$//' {} + \
    && make PYTHON=python3 mnexec \
    && install -m 755 mnexec /usr/bin/mnexec \
    && PIP_BREAK_SYSTEM_PACKAGES=1 python3 -m pip install --no-cache-dir . \
    && install -m 755 docker/entrypoint.sh /usr/local/bin/mininet-entrypoint \
    && install -m 755 docker/sudo-shim.sh /usr/local/bin/sudo \
    && rm -rf build *.egg-info mnexec

ENV MININET_CONTAINER=1
WORKDIR /workspace
ENTRYPOINT ["mininet-entrypoint"]
CMD ["bash"]
