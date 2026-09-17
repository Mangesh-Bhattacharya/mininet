# Run Mininet on macOS (Intel and Apple Silicon)

macOS has no Linux kernel, so Mininet runs in a container or a Linux VM.
Both work natively on Apple Silicon (M1-M4) using `arm64` Linux; no x86
emulation is needed.

| Option | Best for | GUI apps (xterm, MiniEdit) |
|--------|----------|----------------------------|
| **A. Container** (Docker Desktop, OrbStack or Colima) | fastest start, command-line labs | not without extra X server setup |
| **B. Multipass VM** | a full Ubuntu machine with one command | via SSH X forwarding + XQuartz |
| **C. Vagrant or UTM VM** | courses that ship a Vagrantfile, desktop Linux | yes |

---

## A. Container

1. Install one engine:
   - [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/), or
   - [OrbStack](https://orbstack.dev/) (`brew install orbstack`), or
   - [Colima](https://github.com/abiosoft/colima)
     (`brew install colima docker && colima start`)
2. Clone and start:

   ```bash
   git clone https://github.com/Mangesh-Bhattacharya/mininet.git
   cd mininet
   scripts/mininet-docker.sh
   ```

   Inside the container: `mn --test pingall`.

The launcher works with the bash 3.2 that ships with macOS. If the
container VM's kernel lacks the Open vSwitch module, Mininet automatically
uses the OVS userspace datapath (see [docker.md](docker.md)).

---

## B. Multipass

```bash
brew install --cask multipass
git clone https://github.com/Mangesh-Bhattacharya/mininet.git
cd mininet
multipass launch 24.04 --name mininet --cpus 2 --memory 2G --disk 10G \
    --timeout 1800 --cloud-init util/vm/cloud-init.yaml
multipass shell mininet
sudo mn --test pingall
```

The first boot installs Mininet (about 10 minutes). Progress is logged to
`/var/log/mininet-install.log` inside the VM.

---

## C. Vagrant or UTM

- **Vagrant**: install [Vagrant](https://developer.hashicorp.com/vagrant/install)
  and a provider that supports Apple Silicon
  ([VMware Fusion](https://www.vmware.com/products/desktop-hypervisor/workstation-and-fusion),
  [Parallels](https://www.parallels.com/) or VirtualBox 7.1+), then run
  `vagrant up` in the repository. See [virtual-machines.md](virtual-machines.md#vagrant).
- **UTM** (free): create an Ubuntu Server or Desktop 24.04 **ARM64** VM
  using Apple Virtualization, then follow the [Linux instructions](linux.md)
  inside it.

## GUI apps from a VM

Install [XQuartz](https://www.xquartz.org/), log out and back in, then
connect with X forwarding, e.g. `vagrant ssh -- -Y` or
`ssh -Y user@vm-address`, and run `sudo -E mn -x`.
