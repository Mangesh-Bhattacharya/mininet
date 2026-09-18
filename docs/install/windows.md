# Run Mininet on Windows 10/11

Mininet needs a Linux kernel, so on Windows it runs inside Linux. Pick one:

| Option | Best for | GUI apps (xterm, MiniEdit) | Setup time |
|--------|----------|----------------------------|------------|
| **A. WSL 2** (recommended) | coursework, everyday use | yes on Windows 11 (WSLg) | ~10 min |
| **B. Docker Desktop** | quick start, identical setup for a whole class | no (without extra X server setup) | ~5 min once Docker is installed |
| **C. Virtual machine** | isolated lab environment, VirtualBox/VMware/Hyper-V labs | yes | ~15 min |

Run `mn-doctor` in any of them to check your setup.

---

## A. WSL 2 (recommended)

1. Open **PowerShell as Administrator** and install Ubuntu:

   ```powershell
   wsl --install -d Ubuntu-24.04
   ```

   Restart if asked, then launch **Ubuntu 24.04** from the Start menu and
   create your Linux user. If WSL is already installed, update its kernel
   first with `wsl --update`.

2. Inside Ubuntu, clone into your **Linux home directory** (not `/mnt/c`,
   which is slower and breaks file permissions, symlinks and line endings):

   ```bash
   cd ~
   git clone https://github.com/Mangesh-Bhattacharya/mininet.git
   cd mininet
   util/install.sh -nv
   sudo mn-doctor
   sudo mn --test pingall
   ```

3. After a Windows restart or `wsl --shutdown`, Open vSwitch may not be
   running. If `mn` reports `ovs-vsctl: ... database connection failed`:

   ```bash
   sudo service openvswitch-switch start
   ```

   To start it automatically, enable systemd in WSL (the default for new
   installs). Add this to `/etc/wsl.conf` and run `wsl --shutdown` from
   PowerShell:

   ```ini
   [boot]
   systemd=true
   ```

Current WSL 2 kernels (6.x) include the Open vSwitch, bridge, `htb` and
`netem` modules, so the kernel datapath and `--link tc` work. On Windows 11,
`xterm` and MiniEdit windows open directly on your desktop through WSLg:

```bash
sudo mn -x          # one xterm per host
sudo python3 examples/miniedit.py
```

---

## B. Docker Desktop

1. Install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
   and keep the default **"Use the WSL 2 based engine"** setting.
2. Start Docker Desktop, then in PowerShell:

   ```powershell
   git clone https://github.com/Mangesh-Bhattacharya/mininet.git
   cd mininet
   .\scripts\mininet-docker.ps1
   ```

   Inside the container: `mn --test pingall`.

If PowerShell refuses to run scripts, use `scripts\mininet-docker.cmd`
instead, or allow local scripts once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

See [docker.md](docker.md) for all options.

---

## C. Virtual machine

Use [Vagrant](virtual-machines.md#vagrant) (VirtualBox, VMware Workstation or
Hyper-V), [Multipass](virtual-machines.md#multipass) (Hyper-V or VirtualBox),
or create an Ubuntu 24.04 VM by hand and follow the
[Linux instructions](linux.md). Details: [virtual-machines.md](virtual-machines.md).

> **Hyper-V note:** VirtualBox and VMware work alongside Hyper-V/WSL 2 on
> current versions, but nested virtualization is slower. If a VM is very
> slow, prefer WSL 2.

---

## Git on Windows: avoid broken scripts

If you clone with Git for Windows and see `$'\r': command not found` when
running scripts in Linux, Git converted line endings. This repository's
`.gitattributes` prevents that for fresh clones; for older clones:

```powershell
git config core.autocrlf input
git rm -r --cached . ; git reset --hard
```
