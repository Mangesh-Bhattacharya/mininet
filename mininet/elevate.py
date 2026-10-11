"""
Run Mininet's commands as root without asking the user to be an
administrator.

Mininet itself always needs root: it creates network namespaces,
virtual interfaces and Open vSwitch bridges. What it does not need is
for *you* to be an administrator. After

    sudo util/nonroot-setup.sh --user alice

alice belongs to the "mininet" group, and a sudoers rule lets that
group run Mininet's commands with no password. The commands then
re-run themselves as root, so alice types

    mn --test pingall

and never types sudo. Set MININET_NO_SUDO=1 to switch this off.

Without that setup nothing changes: the commands run as they always
have, and tell you what to do if they need root.
"""

import os
import shutil
import subprocess
import sys

# Written by util/nonroot-setup.sh; its presence is what tells the
# commands that re-running themselves as root is expected here
SUDOERS = '/etc/sudoers.d/mininet'

SETUP_HINT = ( 'To use Mininet without typing sudo, an administrator '
               'runs once: sudo util/nonroot-setup.sh --user %s' )


def isRoot():
    "Are we running as root?"
    return hasattr( os, 'geteuid' ) and os.geteuid() == 0


def isLinux():
    "Is this a Linux kernel, the only thing Mininet can build networks on?"
    return sys.platform.startswith( 'linux' )


def userName():
    "The name of the user running this command"
    for name in ( 'SUDO_USER', 'USER', 'LOGNAME' ):
        if os.environ.get( name ):
            return os.environ[ name ]
    try:
        import pwd  # pylint: disable=import-outside-toplevel
        return pwd.getpwuid( os.getuid() ).pw_name
    except ( ImportError, KeyError ):
        return 'youruser'


def setupHint():
    "What to tell someone who needs root and hasn't set this up"
    return SETUP_HINT % userName()


# Where to run a lab when this computer cannot, by platform
ELSEWHERE = {
    'win32': ( 'Windows has no Linux kernel',
               'Design and check labs here, then run them in WSL 2 '
               '(wsl sudo mn-config run %(file)s), in Docker Desktop, '
               'or in a VM - docs/install/windows.md.' ),
    'darwin': ( 'macOS has no Linux kernel',
                'Design and check labs here, then run them in a '
                'container (scripts/mininet-docker.sh) or a Linux VM '
                '- docs/install/macos.md.' ),
}
OTHER_PLATFORM = ( 'this computer is not running Linux',
                   'Mininet builds networks with Linux network '
                   'namespaces: run the lab in Docker or a Linux VM.' )


def blocker( action=None, path=None, what='this command' ):
    """Why can this machine not start a network, and what should the
       person do about it? Returns ( reason, hint ), or ( None, None )
       when nothing is in the way.

       Telling a Windows user to type sudo would be useless advice, so
       the answer depends on the machine. On Linux, action is the
       sentence to tell the reader, e.g. "Run it with: sudo mn ..."."""
    if not isLinux():
        reason, hint = ELSEWHERE.get( sys.platform, OTHER_PLATFORM )
        if '%(file)s' in hint:
            hint = hint % { 'file': os.path.basename( path ) if path
                            else 'lab.yaml' }
        return reason, hint
    if not isRoot():
        return ( '%s is not running as root' % what,
                 '%s - or, to stop typing sudo at all, %s'
                 % ( action or 'Run it with sudo', setupHint() ) )
    return None, None


def commandPath( argv ):
    "The absolute path of the command being run, as sudo sees it"
    name = argv[ 0 ] if argv else ''
    if os.path.dirname( name ):      # already a path, not a bare name
        return os.path.abspath( name )
    return shutil.which( name ) or name


def allowed( command ):
    """Does sudo already let this user run command as root without a
       password? Asks sudo rather than parsing its configuration."""
    sudo = shutil.which( 'sudo' )
    if not sudo:
        return False
    try:
        result = subprocess.run(  # pylint: disable=subprocess-run-check
            [ sudo, '-n', '-l', command ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=10 )
    except ( OSError, subprocess.SubprocessError ):
        return False
    return result.returncode == 0


def canElevate( argv=None ):
    "Could this command re-run itself as root right now?"
    if isRoot() or os.environ.get( 'MININET_NO_SUDO' ):
        return False
    if os.name != 'posix' or not os.path.exists( SUDOERS ):
        return False
    return allowed( commandPath( argv or sys.argv ) )


def elevate( argv=None ):
    """Re-run this command as root through sudo, if the machine has
       been set up for it. Does not return when it succeeds; returns
       False when it could not, so the caller carries on unprivileged.
    """
    argv = list( argv if argv is not None else sys.argv )
    if not canElevate( argv ):
        return False
    sudo = shutil.which( 'sudo' )
    command = commandPath( argv )
    try:
        os.execv( sudo, [ sudo, '-n', command ] + argv[ 1: ] )
    except OSError:
        return False
    return False  # not reached
