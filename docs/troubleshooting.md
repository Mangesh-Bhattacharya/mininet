# Troubleshooting

Start with the doctor. It checks the kernel, Open vSwitch, controllers
and traffic control support, and suggests a command that should work:

```bash
sudo mn-doctor          # add --json for machine-readable output
```

After any crash or Ctrl-C, clean up leftover interfaces and processes:

```bash
sudo mn -c
```

## Open vSwitch

**`ovs-vsctl: unix:/var/run/openvswitch/db.sock: database connection failed`**

Open vSwitch isn't running (common in WSL without systemd, and after
reboots in some VMs):

```bash
sudo service openvswitch-switch start
```

**`*** Open vSwitch kernel module unavailable: using userspace datapath`**

Not an error. The kernel has no `openvswitch` module (typical for Docker
Desktop and some cloud kernels), so Mininet uses the OVS userspace
datapath. It's slower but functionally the same. To force a datapath:

```bash
sudo env MININET_OVS_DATAPATH=kernel mn ...   # or =user
sudo mn --switch ovs,datapath=user ...
```

## Controllers

**`Exception: Could not find a default OpenFlow controller`**

Install the test controller (`util/install.sh -v` does this), use an
external controller, or use a switch that doesn't need one:

```bash
sudo apt-get install openvswitch-testcontroller
sudo mn --controller remote,ip=127.0.0.1,port=6653
sudo mn --switch ovsbr --controller none
```

**`Exception: Please shut down the controller which is running on port 6653`**

The distribution package started its own controller service:

```bash
sudo service openvswitch-testcontroller stop
sudo systemctl disable openvswitch-testcontroller
```

## Installation

**`error: externally-managed-environment`**

You're using an old `install.sh`. Update your clone (`git pull`), which
handles PEP 668 on Ubuntu 23.04+ and Debian 12+.

**`ModuleNotFoundError: No module named 'distutils'`**

Fixed in this fork for Python 3.12+. Reinstall with `util/install.sh -n`.

**`$'\r': command not found` or `/bin/bash^M: bad interpreter`**

The repository was cloned on Windows with CRLF line endings, then used in
Linux. Re-clone inside Linux/WSL, or fix the existing clone:

```bash
git config core.autocrlf input
git rm -r --cached . && git reset --hard
```

**`error: package directory 'mininet/examples' does not exist`**

`mininet/examples` is a symlink, which Git for Windows checks out as a
text file. Clone inside WSL/Linux instead, or recreate it:

```bash
rm mininet/examples && ln -s ../examples mininet/examples
```

## Docker

**`RTNETLINK answers: Operation not permitted`** or
**`mount: permission denied`**

The container isn't privileged. Use the launcher scripts, or add
`--privileged` to `docker run`.

**`docker: Cannot connect to the Docker daemon`** / **`failed to connect to the docker API`**

Start Docker Desktop (Windows/macOS), OrbStack, `colima start`, or
`sudo systemctl start docker` (Linux).

**`--link tc` fails with `RTNETLINK answers: No such file or directory`**

The host kernel (for example the VM behind Docker Desktop) lacks the
`sch_htb` or `sch_netem` qdisc modules. `mn-doctor` reports this. Use WSL 2,
a VM or native Linux for bandwidth, delay and loss experiments.

## Networks

**`Error creating interface pair (s1-eth1,h1-eth0): RTNETLINK answers: File exists`**

Leftovers from a previous run: `sudo mn -c`.

**`pingall` drops packets on the first try**

Switches may still be connecting to the controller or learning MAC
addresses. Run `pingall` again, or start Mininet with `sudo mn --wait`
(`net.waitConnected()` in the Python API).

**xterm: `Can't open display`**

No X server is available. On Windows 11 use WSL 2 (WSLg), on macOS install
XQuartz and use `ssh -Y`, or skip GUI tools with plain `mn`.

Still stuck? Open an issue with the output of `sudo mn-doctor --json` and
`sudo mn -v debug --test pingall`.
