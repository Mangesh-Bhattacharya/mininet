#!/usr/bin/env bash
# Run Mininet in Docker on Linux, macOS or Windows (Git Bash/WSL).
# Compatible with the bash 3.2 that ships with macOS.
#
# Usage: scripts/mininet-docker.sh [options] [command ...]
#
#   (no command)          interactive shell inside the Mininet container
#   mn --test pingall     run a single command and exit
#
# Options:
#   --gui                 start the browser GUI (mn-gui) for lab.yaml in the
#                         current directory, reachable at http://localhost:PORT
#   --port PORT           port for --gui (default 8080)
#   --build               build the image from this checkout instead of
#                         pulling the published one
#   --image NAME          image to use (default: $MININET_IMAGE or
#                         ghcr.io/mangesh-bhattacharya/mininet:latest)
#   --no-mount            don't mount the current directory at /workspace
#   --dry-run             print the docker command instead of running it
#   -h, --help            show this help

set -euo pipefail

IMAGE="${MININET_IMAGE:-ghcr.io/mangesh-bhattacharya/mininet:latest}"
LOCAL_IMAGE="mininet:local"
BUILD=0
MOUNT=1
DRY_RUN=0
GUI=0
PORT=8080
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
    sed -n '2,/^$/s/^# \{0,1\}//p' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --build) BUILD=1; IMAGE="$LOCAL_IMAGE"; shift;;
        --image) IMAGE="$2"; shift 2;;
        --no-mount) MOUNT=0; shift;;
        --gui) GUI=1; shift;;
        --port) PORT="$2"; shift 2;;
        --dry-run) DRY_RUN=1; shift;;
        -h|--help) usage; exit 0;;
        --) shift; break;;
        *) break;;
    esac
done

run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "$*"
    else
        "$@"
    fi
}

if [ "$DRY_RUN" -eq 0 ]; then
    if ! command -v docker > /dev/null 2>&1; then
        echo "Docker is not installed. See docs/install/docker.md" >&2
        exit 1
    fi
    if ! docker info > /dev/null 2>&1; then
        echo "Docker is installed but not running (start Docker Desktop," \
             "OrbStack or Colima, or the docker service)." >&2
        exit 1
    fi
fi

if [ "$BUILD" -eq 1 ]; then
    run docker build -t "$IMAGE" "$REPO_DIR"
elif [ "$DRY_RUN" -eq 0 ] && ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
    echo "Pulling $IMAGE ..." >&2
    if ! docker pull "$IMAGE"; then
        echo "Pull failed; building the image locally instead." >&2
        IMAGE="$LOCAL_IMAGE"
        docker build -t "$IMAGE" "$REPO_DIR"
    fi
fi

case "$PORT" in
    ''|*[!0-9]*) echo "--port needs a number" >&2; exit 2;;
esac
if [ "$GUI" -eq 1 ] && [ "$#" -eq 0 ]; then
    set -- mn-gui --port "$PORT" --config /workspace/lab.yaml
fi

# ${1+"$@"}: an empty "$@" is an unbound variable under set -u in bash 3.2
set -- --rm --privileged --hostname mininet "$IMAGE" ${1+"$@"}
# Interactive terminal only when we have one (not in CI or pipes)
if [ -t 0 ] && [ -t 1 ]; then
    set -- -it "$@"
else
    set -- -i "$@"
fi
if [ "$MOUNT" -eq 1 ]; then
    # Git Bash: pwd -W gives C:/Users/... which Docker Desktop understands
    HOST_PWD="$(pwd -W 2> /dev/null || pwd)"
    set -- -v "$HOST_PWD:/workspace" "$@"
    # Linux hosts: files the container creates in /workspace belong to you,
    # not root (Docker Desktop on macOS/Windows maps ownership itself)
    if [ "$(uname -s)" = "Linux" ] && [ "$(id -u)" -ne 0 ]; then
        set -- -e "MININET_OWNER=$(id -u):$(id -g)" "$@"
    fi
fi
if [ "$GUI" -eq 1 ]; then
    # Loopback only: the GUI can run commands as root in the emulated hosts
    set -- -p "127.0.0.1:$PORT:$PORT" "$@"
fi
if [ "$(uname -s)" = "Linux" ] && [ -d /lib/modules ]; then
    # Lets the container load the host's openvswitch kernel module
    set -- -v /lib/modules:/lib/modules:ro "$@"
    if [ -n "${DISPLAY:-}" ] && [ -d /tmp/.X11-unix ]; then
        set -- -e DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix "$@"
    fi
fi

# Stop Git Bash on Windows from rewriting /workspace into a Windows path
export MSYS_NO_PATHCONV=1
run docker run "$@"
