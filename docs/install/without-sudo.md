# Use Mininet without being an administrator

Mininet needs root privileges: it creates network namespaces, virtual
interfaces and Open vSwitch bridges, and no ordinary user may do that.
What it does **not** need is for *you* to be an administrator, or for
you to type `sudo` at all.

One command, run once by somebody who is an administrator, puts you in
a `mininet` group that may run Mininet's commands as root without a
password. After that:

```bash
mn --test pingall        # no sudo
mn-gui --config lab.yaml # no sudo
```

## Set it up

During installation, `util/install.sh` asks which you want:

```text
Mininet needs root privileges to build networks.
  [1] Use sudo every time   (default, nothing to set up)
  [2] Let alice run Mininet without typing sudo
Choose 1 or 2 [1]:
```

Choose it later, or for somebody else, at any time:

```bash
sudo util/nonroot-setup.sh                      # the user running sudo
sudo util/nonroot-setup.sh --user alice --user bob
util/install.sh -u                              # the same thing
```

Then log out and back in (group membership only applies to new
logins), or start a shell in the new group with `newgrp mininet`.

Check it, or undo it:

```bash
util/nonroot-setup.sh --status
sudo util/nonroot-setup.sh --remove
```

`mn-doctor` also reports it:

```text
[OK]   root        not root, but Mininet may run as root without a
                   password (/etc/sudoers.d/mininet)
```

## What it actually does

1. Creates a system group called `mininet` and adds the users you name.
2. Writes `/etc/sudoers.d/mininet`, checked with `visudo` before it is
   installed, allowing that group to run exactly `mn`, `mn-gui`,
   `mn-config`, `mn-doctor` and `mnexec` as root with no password -
   the absolute paths of the ones installed on the machine, nothing
   else.
3. Mininet's commands notice the file and re-run themselves through
   `sudo -n`, so you never type it.

Nothing else changes: without that file the commands behave exactly as
before, and `MININET_NO_SUDO=1` switches the behaviour off for a single
command or a whole shell.

## The trade-off, stated plainly

**Anyone in the `mininet` group can become root on that machine.**
Mininet runs commands as root inside emulated hosts - that is what it
is for - so being allowed to start it without a password is equivalent
to a root shell. This is the same bargain as the `docker` group.

- On your own laptop or a lab VM: fine, and it saves a lot of typing.
- On a machine shared with people you would not give root to: don't.
  Use `sudo mn` instead, or give each person their own VM or container.

The group is not created unless somebody asks for it, and removing the
rule takes one command.

## Containers and VMs

Inside the Docker image you are already root, so there is nothing to
set up - `mn --test pingall` just works. In a VM, run the setup inside
the VM for the account you log in with.
