#!/bin/bash
# Let people who are not administrators run Mininet.
#
# Mininet always needs root underneath: it creates network namespaces,
# virtual interfaces and Open vSwitch bridges. What it does not need is
# for the person using it to be an administrator. This script, run once
# by someone who is, puts the named users in a "mininet" group and
# installs a sudoers rule letting that group run Mininet's commands
# without a password. After that they type
#
#     mn --test pingall
#
# and never type sudo: the commands re-run themselves as root.
#
#     sudo util/nonroot-setup.sh                 # the user who ran sudo
#     sudo util/nonroot-setup.sh --user alice --user bob
#     sudo util/nonroot-setup.sh --remove        # undo it
#     util/nonroot-setup.sh --status             # is it set up?
#
# SECURITY: anyone in the mininet group can run commands as root
# through Mininet, so this grants them root on this machine. Add only
# people you would give root to anyway - the same bargain as the
# "docker" group. On a shared machine, leave this alone and use sudo.

set -eu

GROUP=mininet
SUDOERS=/etc/sudoers.d/mininet
COMMANDS=( mn mn-gui mn-config mn-doctor mnexec )

usage() {
    sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

status() {
    if [ -f "$SUDOERS" ]; then
        echo "Set up: $SUDOERS exists."
        echo "Members of the $GROUP group: $( getent group "$GROUP" |
            cut -d: -f4 )"
        echo "Allowed commands:"
        grep -E '^Cmnd_Alias' "$SUDOERS" | cut -d= -f2- | tr ',' '\n' |
            sed 's/^ */  /'
    else
        echo "Not set up: Mininet needs sudo on this machine."
        echo "An administrator can change that with:"
        echo "  sudo $0 --user <name>"
    fi
}

needRoot() {
    if [ "$( id -u )" != 0 ]; then
        echo "$0: run this with sudo (it changes /etc)" >&2
        exit 1
    fi
}

remove() {
    needRoot
    rm -f "$SUDOERS"
    echo "Removed $SUDOERS. The $GROUP group is left alone; delete it"
    echo "with: groupdel $GROUP"
    echo "Mininet now needs sudo again."
}

# Absolute paths of the commands, as sudo matches them
commandPaths() {
    local found=() path name
    for name in "${COMMANDS[@]}"; do
        if path=$( command -v "$name" 2> /dev/null ); then
            found+=( "$( readlink -f "$path" )" )
        fi
    done
    ( IFS=, ; echo "${found[*]}" )
}

install_rule() {
    needRoot
    local users=( "$@" ) paths user temp
    if [ ${#users[@]} -eq 0 ]; then
        if [ -n "${SUDO_USER:-}" ]; then
            users=( "$SUDO_USER" )
        else
            echo "$0: no user to set up; pass --user <name>" >&2
            exit 1
        fi
    fi

    paths=$( commandPaths )
    if [ -z "$paths" ]; then
        echo "$0: Mininet is not installed yet (no mn on PATH)." >&2
        echo "Install it first: util/install.sh -nv" >&2
        exit 1
    fi

    getent group "$GROUP" > /dev/null || groupadd --system "$GROUP"
    for user in "${users[@]}"; do
        if ! id "$user" > /dev/null 2>&1; then
            echo "$0: no such user: $user" >&2
            exit 1
        fi
        usermod --append --groups "$GROUP" "$user"
        echo "Added $user to the $GROUP group."
    done

    temp=$( mktemp )
    chmod 0440 "$temp"
    cat > "$temp" <<EOF
# Managed by util/nonroot-setup.sh - members of the $GROUP group may
# run Mininet as root without a password. That is root on this
# machine: add only people you would give root to.
Cmnd_Alias MININET = $paths
Defaults!MININET env_keep += "PYTHONPATH MININET_GUI_TOKEN MININET_GUI_HOST"
%$GROUP ALL=(root) NOPASSWD: MININET
EOF
    # Never install a file that would break sudo for everyone
    if ! visudo --check --file="$temp" > /dev/null; then
        echo "$0: generated sudoers file is not valid; nothing changed" >&2
        visudo --check --file="$temp" >&2 || true
        rm -f "$temp"
        exit 1
    fi
    install -m 0440 -o root -g root "$temp" "$SUDOERS"
    rm -f "$temp"

    echo
    echo "Done. $SUDOERS now lets the $GROUP group run:"
    echo "  ${paths//,/ }"
    echo
    echo "Group membership starts at the next login, so each user"
    echo "should log out and back in (or run: newgrp $GROUP)."
    echo "After that: mn --test pingall  - no sudo needed."
    echo
    echo "NOTE: this gives those users root on this machine, the same"
    echo "way the docker group does. Undo it with: sudo $0 --remove"
}

users=()
while [ $# -gt 0 ]; do
    case "$1" in
        -u|--user)   shift; users+=( "${1:?--user needs a name}" );;
        -r|--remove) remove; exit 0;;
        -s|--status) status; exit 0;;
        -h|--help)   usage 0;;
        *)           echo "$0: unknown option $1" >&2; usage 2;;
    esac
    shift
done

install_rule "${users[@]+"${users[@]}"}"
