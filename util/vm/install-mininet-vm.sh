#!/bin/bash

# This script is intended to install Mininet into
# a brand-new Ubuntu (22.04/24.04) or Debian (12/13) virtual machine,
# to create a fully usable "tutorial" VM.
#
# usage: install-mininet-vm.sh [branch]
#
# Environment:
#   MININET_REPO      git URL to install from (default: mininet/mininet)
#   MININET_VM_CLEAN  set to 1 to scrub the VM for redistribution
#                     (removes SSH host keys, authorized_keys, history
#                     and zeroes free disk space - do NOT use this on a
#                     VM you access via Vagrant/Multipass/cloud SSH keys)
set -e
MININET_REPO=${MININET_REPO:-https://github.com/mininet/mininet.git}
echo "$(whoami) ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/mininet > /dev/null
sudo chmod 0440 /etc/sudoers.d/mininet
echo mininet-vm | sudo tee /etc/hostname > /dev/null
sudo sed -i -e "s/$(hostname)/mininet-vm/g" /etc/hosts
sudo hostname `cat /etc/hostname`
if [ -e /etc/default/grub ]; then
    sudo sed -i -e 's/splash//' /etc/default/grub
    sudo sed -i -e 's/quiet/text/' /etc/default/grub
    sudo update-grub || true
fi
# Update from official archive
sudo apt-get -qq update
# Clean up vmware easy install junk if present
if [ -e /etc/issue.backup ]; then
    sudo mv /etc/issue.backup /etc/issue
fi
if [ -e /etc/rc.local.backup ]; then
    sudo mv /etc/rc.local.backup /etc/rc.local
fi
# Fetch Mininet
sudo apt-get -y -qq install git openssh-server python3
git clone "$MININET_REPO" mininet
# Optionally check out branch
if [ "$1" != "" ]; then
    pushd mininet
    git fetch origin $1
    git checkout $1
    popd
fi
# Install Mininet, Open vSwitch, the OpenFlow Wireshark dissector and POX
time PYTHON=python3 mininet/util/install.sh -nvwp
# Finalize VM (-t: other VM setup, -c: kernel cleanup)
time mininet/util/install.sh -tc
if [ "${MININET_VM_CLEAN:-0}" = 1 ]; then
    time mininet/util/install.sh -d
fi
sudo mn --test pingall
echo "Done preparing Mininet VM."
