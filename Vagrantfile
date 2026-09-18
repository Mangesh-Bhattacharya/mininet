# -*- mode: ruby -*-
# Mininet virtual machine for VirtualBox, VMware, Parallels or libvirt,
# on Windows, macOS (Intel and Apple Silicon) and Linux hosts.
#
#   vagrant up                 # first boot installs Mininet (~10 min)
#   vagrant ssh
#   sudo mn --test pingall
#
# Environment overrides:
#   MININET_BOX     Vagrant box (default bento/ubuntu-24.04, amd64 + arm64)
#   MININET_MEMORY  RAM in MB (default 2048)
#   MININET_CPUS    CPU count (default 2)
#
# See docs/install/virtual-machines.md for provider-specific notes.

BOX = ENV.fetch("MININET_BOX", "bento/ubuntu-24.04")
MEMORY = ENV.fetch("MININET_MEMORY", "2048").to_i
CPUS = ENV.fetch("MININET_CPUS", "2").to_i

Vagrant.configure("2") do |config|
  config.vm.box = BOX
  config.vm.hostname = "mininet-vm"
  config.ssh.forward_x11 = true  # xterm/miniedit via an X server on the host

  # The checkout is copied (not shared) into the VM, so the build works
  # the same regardless of host file system, symlink or line-ending quirks
  config.vm.synced_folder ".", "/vagrant", disabled: true
  config.vm.provision "file", source: ".", destination: "/tmp/mininet-src"

  config.vm.provision "shell", privileged: false, inline: <<-SHELL
    set -e
    rm -rf ~/mininet
    mkdir -p ~/mininet
    cp -a /tmp/mininet-src/. ~/mininet/
    rm -rf /tmp/mininet-src ~/mininet/.git ~/mininet/build ~/mininet/*.egg-info
    cd ~/mininet
    # Undo Windows checkout artifacts: CRLF line endings, symlink-as-file
    find bin util docker examples mininet -type f \\( -name '*.py' -o -name '*.sh' -o -path 'bin/*' \\) \
      -exec sed -i 's/\\r$//' {} +
    sed -i 's/\\r$//' Makefile
    rm -rf mininet/examples && ln -s ../examples mininet/examples
    util/install.sh -nv
    sudo mn-doctor || true
    echo "Mininet is ready: vagrant ssh, then sudo mn --test pingall"
  SHELL

  config.vm.provider "virtualbox" do |vb|
    vb.name = "mininet-vm"
    vb.memory = MEMORY
    vb.cpus = CPUS
  end

  ["vmware_desktop", "vmware_fusion", "vmware_workstation"].each do |vmware|
    config.vm.provider vmware do |v|
      v.vmx["memsize"] = MEMORY.to_s
      v.vmx["numvcpus"] = CPUS.to_s
    end
  end

  config.vm.provider "parallels" do |prl|
    prl.name = "mininet-vm"
    prl.memory = MEMORY
    prl.cpus = CPUS
  end

  config.vm.provider "libvirt" do |lv, override|
    override.vm.box = ENV.fetch("MININET_BOX", "generic/ubuntu2204")
    lv.memory = MEMORY
    lv.cpus = CPUS
  end

  config.vm.provider "hyperv" do |hv, override|
    override.vm.box = ENV.fetch("MININET_BOX", "generic/ubuntu2204")
    hv.memory = MEMORY
    hv.cpus = CPUS
  end
end
