# Install Mininet on Linux (Ubuntu, Debian and derivatives)

Native installation gives the best performance and full access to every
Mininet feature. It is tested in CI on:

| Distribution | Versions |
|--------------|----------|
| Ubuntu | 22.04 LTS, 24.04 LTS (native runners and containers) |
| Debian | 12 "bookworm", 13 "trixie" (containers) |

Derivatives such as Linux Mint, Pop!_OS, Kali and Raspberry Pi OS are
detected as Ubuntu/Debian and generally work. Fedora/RHEL support in
`install.sh` is inherited from upstream and is not tested.

> **Tip:** `install.sh` installs system packages and modifies your system.
> If you'd rather keep your machine untouched, use
> [Docker](docker.md) or a [virtual machine](virtual-machines.md).

## Install

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/Mangesh-Bhattacharya/mininet.git
cd mininet
util/install.sh -nv
```

`-n` installs Mininet and its dependencies, `-v` installs Open vSwitch and
its test controller. That's all most courses need.

Check the installation:

```bash
sudo mn-doctor
sudo mn --test pingall
```

### Optional extras

| Flag | Installs |
|------|----------|
| `-w` | Wireshark with the OpenFlow dissector |
| `-p` | POX controller (into `../pox`) |
| `-f` | OpenFlow 1.0 reference switch/controller (built from source) |
| `-3f` | OpenFlow 1.3 soft switch (ofsoftswitch13, built from source) |
| `-a` | everything used by the classic OpenFlow tutorial (slow) |

Run `util/install.sh -h` for all options. Extras that clone other
projects are placed next to the `mininet` directory, or in `-s <dir>`.

## What changed in install.sh (and why it used to fail)

| Problem on current distributions | Fix |
|----------------------------------|-----|
| `error: externally-managed-environment` from pip on Ubuntu 23.04+/Debian 12+ (PEP 668) | Mininet is installed into the system Python with `PIP_BREAK_SYSTEM_PACKAGES=1`; `pexpect` comes from apt |
| `pep8` package no longer exists, which aborted the whole install | code-check tools are optional and fall back to `pycodestyle` |
| No `python` command on Ubuntu 24.04 / Debian 12 | Python 3 is preferred by default |
| `ModuleNotFoundError: distutils` on Python 3.12+ | `mininet.util` no longer needs `distutils` or `packaging` |
| Failed in minimal images without `lsb_release` or `sudo` | distribution read from `/etc/os-release`; runs as root without `sudo` |
| Only worked if the checkout directory was named `mininet` | paths are relative to the script |
| Open vSwitch not started where there is no systemd | `install.sh -v` starts it if needed |

## Install as a Debian package (.deb)

To install and remove Mininet with `apt` like any other package, build a
`.deb` from your checkout:

```bash
sudo apt-get install -y debhelper dh-python dpkg-dev help2man python3-all python3-setuptools
dpkg-buildpackage -us -uc -b
sudo apt-get install -y ../mininet_*.deb      # pulls in Open vSwitch and friends
sudo mn --test pingall
```

Remove it with `sudo apt-get remove mininet`. CI builds, installs and tests
this package on every change; the built `.deb` is attached to each run of
the [tests workflow](https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/tests.yml)
as the `mininet-deb` artifact.

## Uninstall

```bash
sudo mn -c
sudo python3 -m pip uninstall --break-system-packages -y mininet
sudo rm -f /usr/bin/mnexec /usr/share/man/man1/mn.1 /usr/share/man/man1/mnexec.1
sudo apt-get remove openvswitch-switch openvswitch-testcontroller
```
