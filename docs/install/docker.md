# Run Mininet with Docker (Linux, Windows, macOS)

Docker is the fastest way to get a working Mininet on **any** operating
system, including Apple Silicon Macs. The image contains Mininet, Open
vSwitch and a test OpenFlow controller, and is published for `amd64` and
`arm64`:

```
ghcr.io/mangesh-bhattacharya/mininet:latest
```

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

If the published image can't be pulled (offline, or before the first
release), the launcher builds it locally automatically.

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

- **Linux host with X11**: the launcher forwards `DISPLAY` automatically.
- **Windows / macOS**: GUI apps from containers need extra X server setup.
  For GUI-heavy labs, use [WSL 2](windows.md) (Windows 11 has a built-in X
  server, WSLg) or a [virtual machine](virtual-machines.md) instead.

## Build the image yourself

```bash
docker build -t mininet:local .
scripts/mininet-docker.sh --image mininet:local
```

The Dockerfile repairs checkouts made on Windows (CRLF line endings and
the `mininet/examples` symlink), so building from a Windows clone works.
