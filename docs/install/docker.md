# Run Mininet with Docker (Linux, Windows, macOS)

Docker is the fastest way to get a working Mininet on **any** operating
system, including Apple Silicon Macs. The image contains Mininet, Open
vSwitch and a test OpenFlow controller, and is published for `amd64` and
`arm64`:

```
ghcr.io/mangesh-bhattacharya/mininet:latest   Mininet, GUI, configs in YAML/JSON/Python/C/C++/Ruby
ghcr.io/mangesh-bhattacharya/mininet:full     the same plus Java, C# and COBOL configs (larger)
```

Both are rebuilt every week with the latest Ubuntu security updates,
scanned for vulnerabilities, and signed (see [SECURITY.md](../../SECURITY.md)).

## Quick start without GitHub (Docker only)

You don't need Git or a copy of this repository - only Docker:

```bash
# Mininet shell
docker run --rm -it --privileged ghcr.io/mangesh-bhattacharya/mininet
#   then: mn --test pingall

# Browser GUI for ./lab.yaml (created on first run), at http://localhost:8080
docker run --rm -it --privileged -p 127.0.0.1:8080:8080 -v "$PWD:/workspace" \
  ghcr.io/mangesh-bhattacharya/mininet mn-gui --config /workspace/lab.yaml
```

In Windows PowerShell use `${PWD}` instead of `$PWD`, and put the command
on one line (or end lines with `` ` `` instead of `\`).

Or save this as `compose.yaml` in an empty folder and run
`docker compose up gui` (GUI) or `docker compose run --rm mininet`
(shell):

```yaml
services:
  mininet:
    image: ghcr.io/mangesh-bhattacharya/mininet:latest
    privileged: true
    stdin_open: true
    tty: true
    volumes: ["./workspace:/workspace"]
  gui:
    image: ghcr.io/mangesh-bhattacharya/mininet:latest
    privileged: true
    command: mn-gui --config /workspace/lab.yaml
    ports: ["127.0.0.1:8080:8080"]
    volumes: ["./workspace:/workspace"]
```

`docker compose logs gui` shows the URL with your access token.

Stay up to date: `docker pull ghcr.io/mangesh-bhattacharya/mininet:latest`
(new patched images are published every Monday).

## 1. Install a container engine

| Host | Recommended engine |
|------|--------------------|
| Windows 10/11 | [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with the **WSL 2 backend** |
| macOS (Intel or Apple Silicon) | [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/), [OrbStack](https://orbstack.dev/) or [Colima](https://github.com/abiosoft/colima) |
| Linux | [Docker Engine](https://docs.docker.com/engine/install/) (or Podman with `podman-docker`) |

Start the engine and check that `docker info` works.

## 2. Start Mininet

From a clone of this repository:

| Shell | Command |
|-------|---------|
| Linux / macOS terminal | `scripts/mininet-docker.sh` |
| Windows PowerShell | `.\scripts\mininet-docker.ps1` |
| Windows Command Prompt | `scripts\mininet-docker.cmd` |
| Git Bash / WSL | `scripts/mininet-docker.sh` |

You get a shell inside the container:

```text
root@mininet:/workspace# mn --test pingall
```

The directory you started from is mounted at `/workspace`, so your own
topology scripts are available inside the container:

```bash
mn --custom /workspace/mytopo.py --topo mytopo
python3 /workspace/my_experiment.py
```

Run a single command without an interactive shell:

```bash
scripts/mininet-docker.sh mn --topo tree,depth=2,fanout=2 --test pingall
```

In PowerShell, quote any argument that contains a comma
(`mn --topo 'tree,depth=2,fanout=2'`), because PowerShell treats `a,b` as
an array.

### Launcher options

| Option (bash / PowerShell) | Meaning |
|----------------------------|---------|
| `--build` / `-Build` | build the image from your checkout instead of pulling it |
| `--image NAME` / `-Image NAME` | use a different image |
| `--no-mount` / `-NoMount` | don't mount the current directory |
| `--dry-run` / `-DryRun` | print the `docker run` command without running it |
| `--gui` / `-Gui` | start the browser GUI for `./lab.yaml` |
| `--port N` / `-Port N` | GUI port (default 8080) |

If the published image can't be pulled (offline, or before the first
release), the launcher builds it locally automatically.

### Browser GUI

```bash
scripts/mininet-docker.sh --gui                # PowerShell: .\scripts\mininet-docker.ps1 -Gui
```

opens the [GUI](../gui.md) for `lab.yaml` in your current directory on
`http://localhost:8080` (the exact URL, with its access token, is printed).
The port is published on `127.0.0.1` only. `--port 9000` / `-Port 9000`
changes it.

### Without the launcher

```bash
docker run --rm -it --privileged ghcr.io/mangesh-bhattacharya/mininet
# or, from the repository root:
docker compose run --rm mininet
```

`--privileged` is required: Mininet creates network namespaces, virtual
Ethernet pairs and Open vSwitch bridges, which an unprivileged container
is not allowed to do.

## How the container adapts to your host

Mininet uses the **host's Linux kernel**. On Windows and macOS that is the
small Linux VM Docker runs in.

- **Linux hosts**: the launcher mounts `/lib/modules`, so Open vSwitch uses
  the fast `openvswitch` kernel datapath.
- **Docker Desktop, OrbStack, Colima**: if the kernel module isn't
  available, the container starts Open vSwitch with its **userspace
  datapath** and Mininet uses it automatically (you'll see
  `datapath: user` in the banner). Everything works, but throughput is
  lower, so don't use it for performance measurements.

Run `mn-doctor` inside the container to see exactly what your host
supports (for example, whether `--link tc` bandwidth/delay shaping is
available).

## GUI tools (xterm, MiniEdit, Wireshark)

For a GUI on any host, use the browser-based [`mn-gui`](../gui.md)
(above): it needs no X server. The X11 desktop tools below are optional.

- **Linux host with X11**: the launcher forwards `DISPLAY` automatically.
- **Windows / macOS**: GUI apps from containers need extra X server setup.
  For GUI-heavy labs, use [WSL 2](windows.md) (Windows 11 has a built-in X
  server, WSLg) or a [virtual machine](virtual-machines.md) instead.

## Verify the image signature

```bash
cosign verify ghcr.io/mangesh-bhattacharya/mininet:latest \
  --certificate-identity-regexp '^https://github.com/Mangesh-Bhattacharya/mininet/\.github/workflows/docker\.yml@' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Build the image yourself

```bash
docker build -t mininet:local .
docker build --build-arg CONFIG_LANGUAGES=full -t mininet:local-full .   # + Java, C#, COBOL
scripts/mininet-docker.sh --image mininet:local
```

The Dockerfile repairs checkouts made on Windows (CRLF line endings and
the `mininet/examples` symlink), so building from a Windows clone works.
