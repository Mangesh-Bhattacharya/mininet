# Run Mininet in a virtual machine

A VM gives every student the same isolated Linux environment, on Windows,
macOS or Linux, and can't break the host system.

- [Vagrant](#vagrant): one command, works with VirtualBox, VMware,
  Parallels, Hyper-V and libvirt
- [Multipass](#multipass): lightweight Ubuntu VMs on Windows, macOS and Linux
- [Any hypervisor, by hand](#any-hypervisor-by-hand): VirtualBox, VMware,
  UTM, Hyper-V, Proxmox, GNOME Boxes, cloud instances
- [Building a VM image to distribute to a class](#building-a-tutorial-vm-for-a-class)

Recommended VM size: **2 vCPUs, 2 GB RAM, 10 GB disk**.

## Vagrant

```bash
git clone https://github.com/Mangesh-Bhattacharya/mininet.git
cd mininet
vagrant up            # first boot installs Mininet (~10 minutes)
vagrant ssh
sudo mn --test pingall
```

| Provider | Hosts | Command |
|----------|-------|---------|
| VirtualBox 7.x | Windows, Linux, Intel Mac (7.1+: Apple Silicon) | `vagrant up` |
| VMware Workstation/Fusion | Windows, Linux, macOS | `vagrant up --provider vmware_desktop` (needs the [vagrant-vmware-utility](https://developer.hashicorp.com/vagrant/install/vmware)) |
| Parallels | macOS | `vagrant up --provider parallels` (needs `vagrant plugin install vagrant-parallels`) |
| Hyper-V | Windows Pro/Education | `vagrant up --provider hyperv` (elevated shell) |
| libvirt/KVM | Linux | `vagrant up --provider libvirt` (needs `vagrant-libvirt`) |

The default box is `bento/ubuntu-24.04` (amd64 and arm64). Hyper-V and
libvirt default to `generic/ubuntu2204`. Override with environment
variables:

```bash
MININET_BOX=bento/debian-12 MININET_MEMORY=4096 MININET_CPUS=4 vagrant up
```

Your checkout is copied into the VM at `~/mininet` during provisioning.
To pick up later changes, run `vagrant provision`.

## Multipass

[Install Multipass](https://canonical.com/multipass/install), then:

```bash
multipass launch 24.04 --name mininet --cpus 2 --memory 2G --disk 10G \
    --timeout 1800 --cloud-init util/vm/cloud-init.yaml
multipass shell mininet
sudo mn --test pingall
```

On Windows, run the same command in PowerShell as one line (or replace
`\` with a backtick). `util/vm/cloud-init.yaml` also works as **user data**
on AWS, Azure, GCP, DigitalOcean and similar clouds for Ubuntu 22.04/24.04
images.

## Any hypervisor, by hand

1. Create a VM from an **Ubuntu Server 24.04** or **Debian 12/13** ISO
   (ARM64 image on Apple Silicon).
2. Inside the VM:

   ```bash
   sudo apt-get update && sudo apt-get install -y git
   git clone https://github.com/Mangesh-Bhattacharya/mininet.git
   cd mininet
   util/install.sh -nv
   sudo mn --test pingall
   ```

Mininet works fine without a desktop. To use `xterm`, MiniEdit or
Wireshark, either install a desktop (`sudo apt-get install ubuntu-desktop-minimal`)
or connect with SSH X forwarding (`ssh -Y`) from a host with an X server
(built in on Linux, XQuartz on macOS, MobaXterm or VcXsrv on Windows).

## Using the browser GUI from your computer

Run `mn-gui` inside the VM and reach it through an SSH tunnel, which
keeps it off the network and encrypts it:

```bash
vagrant ssh -- -L 8080:localhost:8080            # or: ssh -L 8080:localhost:8080 user@vm
sudo mn-gui --config lab.yaml                    # inside the VM
```

Then open the printed `http://localhost:8080/#token=...` URL on your
computer. See [gui.md](../gui.md).

## Building a tutorial VM for a class

`util/vm/install-mininet-vm.sh` turns a fresh Ubuntu/Debian VM into the
classic Mininet tutorial VM (Mininet, Open vSwitch, Wireshark with the
OpenFlow dissector, POX, passwordless sudo, hostname `mininet-vm`):

```bash
wget https://raw.githubusercontent.com/Mangesh-Bhattacharya/mininet/master/util/vm/install-mininet-vm.sh
bash install-mininet-vm.sh
```

Before exporting the VM (OVA/VMDK/QCOW2) for students, you can scrub SSH
keys and shell history and zero free space for a smaller image:

```bash
MININET_VM_CLEAN=1 bash install-mininet-vm.sh
```

Only do this on an image you are about to export: it deletes SSH host keys
and `authorized_keys`, which would lock Vagrant, Multipass or cloud SSH
access out of the running VM.
