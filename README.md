Mininet: Rapid Prototyping for Software Defined Networks
========================================================
*The best way to emulate almost any network on your laptop, now on
Linux, Windows, macOS and virtual machines.*

Mininet 2.3.1b4 &middot; cross-platform edition

[![tests](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/tests.yml/badge.svg)](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/tests.yml)
[![install-matrix](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/install-matrix.yml/badge.svg)](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/install-matrix.yml)
[![docker](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/docker.yml/badge.svg)](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/docker.yml)
[![launchers](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/launchers.yml/badge.svg)](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/launchers.yml)
[![License: BSD](https://img.shields.io/badge/license-BSD-blue.svg)](LICENSE)

> This is a community-maintained fork of
> [mininet/mininet](https://github.com/mininet/mininet). It keeps
> Mininet's code and Python API compatible with upstream and adds
> installation, packaging and documentation so that students and the
> public can get Mininet running on the machine they already have. It is
> not an official Mininet release; all credit for Mininet itself goes to
> the [Mininet contributors](CONTRIBUTORS).

### Why This Exists

Mininet is still the standard teaching tool for SDN and OpenFlow, but
its last upstream release predates current operating systems, and in
2026 a first-time user typically hits a wall:

- `util/install.sh` aborts on Ubuntu 24.04 and Debian 12/13 (PEP 668
  `externally-managed-environment`, removed `pep8` package, no `python`).
- `mn` crashes on Python 3.12+ (`No module named 'distutils'`).
- There is no supported path for **Windows** or **macOS** users (most
  students), and the prebuilt VM images are years old and x86-only, so
  they don't run on Apple Silicon Macs.
- CI targeted retired Ubuntu 20.04 runners and Python 2.

This fork fixes those problems without changing how Mininet works, and
tests every supported path in CI.

---

### Pick your platform

| Your computer | Quickest start | Full Linux experience (GUI tools, best performance) |
|---------------|----------------|------------------------------------------------------|
| **Ubuntu / Debian** | [Native install](docs/install/linux.md): `util/install.sh -nv` | same |
| **Windows 10/11** | [Docker Desktop](docs/install/docker.md): `.\scripts\mininet-docker.ps1` | [WSL 2](docs/install/windows.md) |
| **macOS** (Intel or Apple Silicon) | [Docker/OrbStack/Colima](docs/install/docker.md): `scripts/mininet-docker.sh` | [Multipass, UTM or Vagrant VM](docs/install/macos.md) |
| **Any OS, isolated VM** | [Vagrant](docs/install/virtual-machines.md#vagrant): `vagrant up` | [Multipass / any hypervisor](docs/install/virtual-machines.md) |

#### Linux (Ubuntu 22.04/24.04, Debian 12/13)

```bash
git clone https://github.com/Mangesh-Bhattacharya/mininet.git
cd mininet
util/install.sh -nv
sudo mn --test pingall
```

#### Windows, macOS or Linux with Docker

```bash
git clone https://github.com/Mangesh-Bhattacharya/mininet.git
cd mininet
scripts/mininet-docker.sh          # Windows PowerShell: .\scripts\mininet-docker.ps1
mn --test pingall                  # inside the container
```

#### Virtual machine (VirtualBox, VMware, Parallels, Hyper-V, libvirt)

```bash
git clone https://github.com/Mangesh-Bhattacharya/mininet.git
cd mininet
vagrant up && vagrant ssh
sudo mn --test pingall
```

### Check your setup with `mn-doctor`

`mn-doctor` explains what works on the current machine and suggests a
command line that will work there:

```text
$ sudo mn-doctor
Mininet doctor (environment: wsl)

[ ok ] linux       Linux kernel 6.6.87.2-microsoft-standard-WSL2 (wsl)
[ ok ] root        running as root
[ ok ] python      Python 3.12
[ ok ] netns       network namespaces supported
[ ok ] mnexec      found /usr/bin/mnexec
[ ok ] ovs         Open vSwitch is running
[ ok ] ovs-kernel  openvswitch kernel datapath available
[ ok ] controller  OpenFlow controller: ovs-testcontroller
[ ok ] bridge      Linux bridge available
[ ok ] tc          traffic control (htb, netem) available

Try: sudo mn --test pingall
```

Run on Windows or macOS directly, it tells you to use Docker, WSL 2 or a
VM. `mn-doctor --json` produces the same report for scripts and graders.

New to Mininet? Follow [docs/getting-started.md](docs/getting-started.md).
Something broken? See [docs/troubleshooting.md](docs/troubleshooting.md).

---

### What is Mininet?

Mininet emulates a complete network of hosts, links, and switches
on a single machine. To create a sample two-host, one-switch network,
just run:

  `sudo mn`

Mininet is useful for interactive development, testing, and demos,
especially those using OpenFlow and SDN. OpenFlow-based network
controllers prototyped in Mininet can usually be transferred to
hardware with minimal changes for full line-rate execution.

### How does it work?

Mininet creates virtual networks using process-based virtualization
and network namespaces - features that are available in recent Linux
kernels. In Mininet, hosts are emulated as `bash` processes running in
a network namespace, so any code that would normally run on a Linux
server (like a web server or client program) should run just fine
within a Mininet "Host". The Mininet "Host" will have its own private
network interface and can only see its own processes. Switches in
Mininet are software-based switches like Open vSwitch or the OpenFlow
reference switch. Links are virtual ethernet pairs, which live in the
Linux kernel and connect our emulated switches to emulated hosts
(processes).

Because Mininet depends on the Linux kernel, on Windows and macOS it runs
inside Linux: a WSL 2 distribution, the Linux VM behind Docker, or a
virtual machine.

### Features

* A command-line launcher (`mn`) to instantiate networks.
* A handy Python API for creating networks of varying sizes and
  topologies.
* Examples (in the `examples/` directory) to help you get started.
* Full API documentation via Python `help()` docstrings, as well as
  the ability to generate PDF/HTML documentation with `make doc`.
* Parametrized topologies (`Topo` subclasses), e.g.
  `mn --topo tree,depth=2,fanout=3`
* A command-line interface (`CLI` class) with diagnostic commands (like
  `iperf` and `ping`) and the ability to run a command on a node, e.g.
  `mininet> h1 ifconfig -a`
* A cleanup command for leftover interfaces and processes: `mn -c`

### What's different in this fork

| Area | Change |
|------|--------|
| Python | Works on Python 3.9-3.13 without `distutils` or `packaging`; Python 3 is the default everywhere |
| `install.sh` | Ubuntu 22.04/24.04 and Debian 12/13 support (PEP 668, renamed packages, `/etc/os-release`, containers without `sudo`, checkout directory can have any name) |
| Open vSwitch | Falls back to the userspace datapath automatically when the `openvswitch` kernel module is unavailable (`MININET_OVS_DATAPATH` to override) |
| Docker | Multi-arch image (`amd64`, `arm64`) on GHCR, entrypoint that starts OVS, launchers for bash, PowerShell and `cmd` |
| VMs | `Vagrantfile` (VirtualBox, VMware, Parallels, Hyper-V, libvirt), Multipass/cloud-init config, updated tutorial VM script |
| Diagnostics | `mn-doctor` environment checker (text and JSON) |
| CI | Native Ubuntu 22.04/24.04, Debian 12/13 and Ubuntu containers, Docker image on amd64 + arm64, launchers on macOS and Windows |
| Line endings | `.gitattributes` keeps scripts runnable when cloned on Windows |

The `mininet` Python package and `mn` command-line options are unchanged,
so existing course material, custom topologies and controller setups
keep working.

### What CI verifies

| Platform | What runs |
|----------|-----------|
| Ubuntu 22.04, 24.04 (native) | `install.sh`, `mn-doctor`, `pingall` with OVS kernel and userspace datapaths, Linux bridge, TCLink, core test suite |
| Ubuntu 24.04 | examples test suite, tutorial VM script |
| Ubuntu 22.04/24.04, Debian 12/13 (containers) | `install.sh` from scratch, then `pingall` and `iperf` |
| Docker image, amd64 and arm64 | build, then `pingall` with userspace and kernel datapaths, and the launcher |
| macOS | bash 3.2 launcher, `mn-doctor` guidance |
| Windows | PowerShell 7, Windows PowerShell 5.1, `cmd` and Git Bash launchers, `mn-doctor` guidance |
| Python 3.9-3.13 | module imports, `mn-doctor` unit tests |

GitHub's macOS and Windows runners can't run Linux containers, so the
Mininet networks themselves are exercised on Linux, which is where they
run on every platform.

### Documentation

* Installation: [Linux](docs/install/linux.md) &middot;
  [Windows](docs/install/windows.md) &middot;
  [macOS](docs/install/macos.md) &middot;
  [Docker](docs/install/docker.md) &middot;
  [Virtual machines](docs/install/virtual-machines.md)
* [Getting started](docs/getting-started.md) and
  [Troubleshooting](docs/troubleshooting.md)
* The original [`INSTALL`](INSTALL) notes
* Upstream documentation: the [Mininet website](http://mininet.org),
  [walkthrough](http://mininet.org/walkthrough/),
  [Python API introduction](https://github.com/mininet/mininet/wiki/Introduction-to-Mininet)
  and [FAQ](https://github.com/mininet/mininet/wiki/FAQ)

### Contributing

Bug reports and pull requests for installation problems on a platform
not covered above are especially welcome. Please include the output of
`sudo mn-doctor --json`. Fixes to Mininet's core that aren't specific to
this fork are best proposed [upstream](https://github.com/mininet/mininet)
too.

### Credits and license

Mininet is developed by Bob Lantz, Brandon Heller, Nikhil Handigol and
the [Mininet contributors](CONTRIBUTORS), and is distributed under the
BSD-style [LICENSE](LICENSE). The cross-platform packaging, tooling and
documentation in this fork are maintained by
[Mangesh Bhattacharya](https://github.com/Mangesh-Bhattacharya) under the
same license.
