# Mininet in a container: runs on Linux, Windows (Docker Desktop/WSL2)
# and macOS (Docker Desktop, OrbStack, Colima) on amd64 and arm64.
#
#   docker run --rm -it --privileged ghcr.io/mangesh-bhattacharya/mininet
#   docker run --rm -it --privileged -p 127.0.0.1:8080:8080 \
#       ghcr.io/mangesh-bhattacharya/mininet mn-gui       # browser GUI
#
#   docker build -t mininet .                          # build it yourself
#   docker build --build-arg CONFIG_LANGUAGES=full -t mininet:full .
#
# --privileged is required: Mininet creates network namespaces,
# veth pairs and Open vSwitch bridges. See docs/install/docker.md and
# SECURITY.md.
#
# The base image is pinned by digest; Dependabot proposes a new digest
# every week, and the weekly scheduled build also installs every
# pending Ubuntu security update (apt-get upgrade below).

FROM ubuntu:24.04@sha256:b3cc40b72b93588182b5410f723c7aaf142363311c2aa993d8a453ddcbb3ae15

ARG DEBIAN_FRONTEND=noninteractive
# Toolchains for configuration files written as programs:
#   standard: Python, C, C++ and Ruby
#   full:     also Java, C# (.NET) and COBOL (a much larger image)
ARG CONFIG_LANGUAGES=standard

LABEL org.opencontainers.image.title="Mininet" \
      org.opencontainers.image.description="Mininet network emulator with Open vSwitch, a browser GUI and multi-language lab configurations" \
      org.opencontainers.image.source="https://github.com/Mangesh-Bhattacharya/mininet" \
      org.opencontainers.image.licenses="BSD-3-Clause"

# hadolint ignore=DL3005,DL3008
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        bridge-utils ca-certificates curl ethtool g++ gcc help2man iperf iperf3 \
        iproute2 iputils-ping kmod libc6-dev make net-tools nano \
        openvswitch-switch openvswitch-testcontroller procps psmisc python3 \
        python3-packaging python3-pexpect python3-pip python3-yaml ruby \
        socat tcpdump telnet vim-tiny xterm \
    && if [ "$CONFIG_LANGUAGES" = "full" ]; then \
        apt-get install -y --no-install-recommends \
            default-jdk-headless dotnet-sdk-8.0 gnucobol; \
    fi \
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
    && rm -rf build ./*.egg-info mnexec

ENV MININET_CONTAINER=1 \
    MININET_GUI_HOST=0.0.0.0 \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_NOLOGO=1
# mn-gui. Publish it to the host's loopback only: -p 127.0.0.1:8080:8080
EXPOSE 8080
WORKDIR /workspace
ENTRYPOINT ["mininet-entrypoint"]
CMD ["bash"]
