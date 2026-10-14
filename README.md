<h1 align="center">Mininet</h1>

<p align="center">
  Build a working computer network on your own machine, in about a second.
</p>

<p align="center">
  <a href="https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/tests.yml"><img alt="tests" src="https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/tests.yml/badge.svg"></a>
  <a href="https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/install-matrix.yml"><img alt="install-matrix" src="https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/install-matrix.yml/badge.svg"></a>
  <a href="https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/docker.yml"><img alt="docker" src="https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/docker.yml/badge.svg"></a>
  <a href="https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/security-audit.yml"><img alt="security-audit" src="https://github.com/Mangesh-Bhattacharya/mininet/actions/workflows/security-audit.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: BSD-3-Clause" src="https://img.shields.io/badge/license-BSD--3--Clause-blue.svg"></a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/gui-pingall-dark.png">
    <img src="docs/images/gui-pingall.png" width="900"
         alt="The browser GUI: four hosts and two switches drawn on a canvas, with a matrix on the right showing every host can reach every other host">
  </picture>
</p>

Mininet makes real hosts, switches and links out of Linux network
namespaces. The packets are real, the commands are the ones you would
type on a real machine, and when you quit it all disappears. People use
it to learn networking, to try SDN and OpenFlow ideas, and to run labs
for a class.

This fork keeps `mn`, the Python API and every existing tutorial working
exactly as before. What it adds is a way in: it installs on Windows and
macOS as well as Linux, it has a browser GUI, you can describe a lab in
a file instead of code, and students don't need an administrator
account.

## Install

**Docker, on any machine.** Install
[Docker Desktop](https://docs.docker.com/get-docker/), then:

```bash
docker run --rm -it --privileged ghcr.io/mangesh-bhattacharya/mininet
```

```text
root@mininet:/workspace# mn --test pingall
*** Results: 0% dropped (2/2 received)
```

**Ubuntu or Debian.** Tested on Ubuntu 22.04, 24.04, 26.04 and Debian
12 and 13:

```bash
git clone https://github.com/Mangesh-Bhattacharya/mininet.git
cd mininet
util/install.sh -nv
sudo mn --test pingall
```

**Windows.** Easiest is Docker Desktop and the command above, or
`.\scripts\mininet-docker.ps1 -Gui` from a clone. If you want the full
thing, install Ubuntu under WSL 2 and follow the Linux steps. Details in
[docs/install/windows.md](docs/install/windows.md).

**macOS.** Same Docker command (Intel and Apple Silicon), or a Linux VM
with Multipass, UTM or Vagrant. See
[docs/install/macos.md](docs/install/macos.md).

**A VM.** `vagrant up && vagrant ssh` in a clone works with VirtualBox,
VMware, Parallels, Hyper-V and libvirt.

Not sure what your machine can do? Run `mn-doctor`. It checks what is
missing and prints a command that will work, including on Windows and
macOS where Mininet itself cannot run.

## Your first lab

A lab is one file. Create one and open it in the browser:

```bash
mn-config init --lang yaml -o lab.yaml
sudo mn-gui --config lab.yaml
```

`mn-gui` prints a URL with an access token in it. Open that, and you get
the topology on the left and the file on the right. Change either one
and the other keeps up.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/gui-overview-dark.png">
  <img src="docs/images/gui-overview.png"
       alt="The GUI with a topology of three hosts and two switches on the left and the YAML file that describes it on the right">
</picture>

The palette down the left side is MiniEdit's: select, host, switch,
legacy switch, legacy router, link, controller, delete. Drop a device on
the canvas, click two devices to link them, and fill in addresses or
link speeds underneath. Everything you do is written to the lab file as
you go, so you can keep it in git and hand it to someone else.

<img src="docs/images/gui-editor.png"
     alt="Adding a fourth host, linking it to a switch, and giving it an IP address in the properties form below the canvas">

Mistakes are caught while you type, with a hint for each one, and
**Save** stays off until the file is valid. You can't save a broken lab
by accident.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/gui-validation-dark.png">
  <img src="docs/images/gui-validation.png"
       alt="Two problems listed under the editor, each with a hint, and a disabled Save button">
</picture>

Press **Run** and the network starts. **Ping all** fills in a matrix of
who can reach whom, and the Console tab gives you a shell on any host,
or an iperf measurement between two of them.

Along the bottom is the activity log. Every command the lab ran is in
it, with its output, and every error comes with a line saying what to
try. If you press a button that can't do its job, it tells you why
rather than doing nothing, and the answer suits your machine: on Windows
it points at WSL 2 or Docker instead of telling you to type `sudo`,
which wouldn't help.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/gui-activity-dark.png">
  <img src="docs/images/gui-activity.png"
       alt="The activity drawer showing 'Run: nothing happened' with the suggestion 'The network is not running: press Run first.'">
</picture>

The GUI only listens on `127.0.0.1`, needs the token it printed, and
loads nothing from the internet. [docs/gui.md](docs/gui.md) covers the
rest, including reaching it over SSH on a VM.

## Lab files

The file the GUI edits is just text, and you can work on it directly:

```bash
mn-config validate lab.yaml     # check it, no root needed
sudo mn-config run lab.yaml     # start it, run its tests, open the CLI
```

```yaml
version: 1                  # [FIXED]    don't change
name: two-switch-lab        # [EDIT]     your lab
network:
  controller: default       # [EDIT]     default | remote | none
  datapath: auto            # [ADVANCED] leave on auto
hosts:
  - { name: h1, ip: 10.0.0.1/24 }
  - { name: h2, ip: 10.0.0.2/24 }
switches: [ { name: s1 }, { name: s2 } ]
links:
  - [h1, s1]
  - [h2, s2]
  - { from: s1, to: s2, bw: 10, delay: 5ms }   # 10 Mbit/s, 5 ms
tests: [pingall]
```

Every setting is marked `[EDIT]`, `[ADVANCED]` or `[FIXED]` so nobody
has to guess which ones are safe to touch. Problems come back all at
once, with a hint:

```text
$ mn-config validate lab.yaml
Configuration problems:
  - netwrok: unknown setting
    hint: did you mean "network"?
  - links[2].to: unknown node 's9'
    hint: define it under hosts or switches first
```

If YAML isn't your thing, write the same lab in JSON, Python, C, C++,
C#, Java, Ruby or COBOL (`mn-config init --lang java`). They all produce
the same network and pass the same checks; program configs are compiled
and run as you, never as root. `run` exits non-zero when a test fails,
so `mn-config run lab.yaml --no-cli` works in a script or an autograder.
Everything you can put in a lab file:
[docs/configuration.md](docs/configuration.md).

You don't need Linux to write one. `pip install ".[yaml]"` on Windows or
macOS gets you `mn-config` and `mn-gui`; the GUI opens in edit-only mode
and tells you where to run the finished lab.

## Running without an administrator account

Mininet needs root to make network namespaces. The person using it does
not have to be an administrator, or type `sudo` at all:

```bash
sudo util/nonroot-setup.sh --user alice   # once, by an admin
mn --test pingall                         # from then on, as alice
```

`util/install.sh` offers this at the end of an install, or run it later
with `util/install.sh -u`. It adds the user to a `mininet` group and one
`sudoers` rule, so the commands re-run themselves as root. That does
give that user root by way of Mininet, much as the `docker` group does.
The trade-off and how to undo it:
[docs/install/without-sudo.md](docs/install/without-sudo.md).

## The command line still works

```bash
sudo mn                                           # 2 hosts, 1 switch, interactive CLI
sudo mn --topo tree,depth=2,fanout=3 --test pingall
sudo mn --link tc,bw=10,delay=5ms                 # shaped links
mininet> h1 ping -c3 h2
mininet> iperf h1 h2
```

Nothing here changed, so tutorials written for upstream Mininet work as
written. If you are new to it, start with
[docs/getting-started.md](docs/getting-started.md).

## What's in the box

`mn` and the Python API, unchanged. `mn-config` for lab files,
`mn-gui` for the browser, `mn-doctor` for when something is wrong.
MiniEdit, the original desktop editor, is still in `examples/`. There is
a Docker image (`latest`, or `full` for the Java, C# and COBOL
toolchains), launcher scripts for all three operating systems, a
`Vagrantfile` and cloud-init for VMs, and a `debian/` directory if you
want a `.deb`.

## If something breaks

Run `mn-doctor`. If that doesn't explain it,
[docs/troubleshooting.md](docs/troubleshooting.md) covers the common
ones, and an issue with the output of `mn-doctor --json` attached is
always welcome.

Every platform in this table is tested on each change and again weekly:
Ubuntu 22.04/24.04/26.04 and Debian 12/13 from a clean container, the
Docker image on amd64 and arm64, the GUI driven by a real browser in
light and dark mode, all nine config languages, the Debian package, the
OpenFlow reference switch on gcc 13 and 15, the Windows and macOS
launchers, and Python 3.9 through 3.14.

## Security

Images are rebuilt every Monday with the current Ubuntu security
updates, and Dependabot proposes updates as they appear; an update whose
tests pass merges itself. On the 1st and 15th of each month a deeper
audit runs ClamAV over the source and the published image, OSV against
the dependencies, gitleaks over the whole git history, and Trivy against
the image. Each check is tied to the
[MITRE ATT&CK](docs/security/attack-coverage.md) technique it defends
against, and a finding opens an issue by itself.

Images with a fixable high or critical vulnerability are never
published. The ones that are get signed with cosign and carry an SBOM
and build provenance, so you can check one before running it:

```bash
cosign verify ghcr.io/mangesh-bhattacharya/mininet:latest \
  --certificate-identity-regexp '^https://github.com/Mangesh-Bhattacharya/mininet/\.github/workflows/docker\.yml@' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Mininet needs root and `--privileged`, so run labs on a lab machine, a
VM or a container rather than something you care about. Found a
vulnerability? [SECURITY.md](SECURITY.md) says how to report it
privately.

## Documentation

Install: [Linux](docs/install/linux.md) ·
[Windows](docs/install/windows.md) · [macOS](docs/install/macos.md) ·
[Docker](docs/install/docker.md) ·
[Virtual machines](docs/install/virtual-machines.md) ·
[Without sudo](docs/install/without-sudo.md)

Use: [Getting started](docs/getting-started.md) ·
[Lab files](docs/configuration.md) · [Browser GUI](docs/gui.md) ·
[Troubleshooting](docs/troubleshooting.md)

Also: [Security policy](SECURITY.md) ·
[ATT&CK coverage](docs/security/attack-coverage.md) ·
[Mininet-AI research notes](docs/research/mininet-ai.md) ·
[mininet.org](http://mininet.org) ·
[Upstream walkthrough](http://mininet.org/walkthrough/)

## Credits

Mininet is the work of Bob Lantz, Brandon Heller, Nikhil Handigol and
the [Mininet contributors](CONTRIBUTORS). This edition (the installers,
Docker image, VM tooling, `mn-doctor`, `mn-config`, `mn-gui`, the
documentation and the security automation) is maintained by
[Mangesh Bhattacharya](https://github.com/Mangesh-Bhattacharya). General
fixes go upstream too, such as
[mininet/mininet#1256](https://github.com/mininet/mininet/pull/1256).
Both are under the [BSD 3-Clause License](LICENSE).

Pull requests are welcome, especially for an install that didn't work on
your machine.
