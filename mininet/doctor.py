"""
Mininet doctor: check whether this machine can run Mininet, and
suggest a working command line.

Usage:
  sudo mn-doctor            # human-readable report
  sudo mn-doctor --json     # machine-readable report
  sudo python3 -m mininet.doctor

Mininet needs a Linux kernel (network namespaces, veth pairs) and
root privileges. On Windows and macOS it runs inside WSL2, a Docker
container or a Linux virtual machine; this script reports which of
those environments it detects and what (if anything) is missing.
"""

import io
import json
import os
import platform
import shlex
import sys
from subprocess import Popen, PIPE, STDOUT

OK, WARN, FAIL, INFO = 'ok', 'warn', 'fail', 'info'


class Env( object ):
    "Access to the system under test (replaced by a fake in unit tests)"

    @staticmethod
    def system():
        "Operating system name, e.g. Linux"
        return platform.system()

    @staticmethod
    def exists( path ):
        "Does path exist?"
        return os.path.exists( path )

    @staticmethod
    def read( path ):
        "Return contents of path, or '' if unreadable"
        try:
            with io.open( path, encoding='utf-8', errors='replace' ) as f:
                return f.read()
        except ( IOError, OSError ):
            return ''

    @staticmethod
    def which( cmd ):
        "Return path to cmd, or None"
        for path in os.environ.get( 'PATH', '' ).split( os.pathsep ) + [
                '/usr/sbin', '/sbin', '/usr/local/sbin' ]:
            candidate = os.path.join( path, cmd )
            if os.path.isfile( candidate ) and os.access( candidate,
                                                          os.X_OK ):
                return candidate
        return None

    @staticmethod
    def run( cmd ):
        "Run a command (no shell); return ( exitcode, output )"
        try:
            # pylint: disable=consider-using-with
            popen = Popen( shlex.split( cmd ), stdout=PIPE, stderr=STDOUT )
            out, _err = popen.communicate()
            return popen.returncode, out.decode( 'utf-8', 'replace' )
        except OSError as e:
            return 127, str( e )

    @staticmethod
    def isRoot():
        "Are we running as root?"
        return hasattr( os, 'geteuid' ) and os.geteuid() == 0

    @staticmethod
    def pythonVersion():
        "( major, minor ) of running Python"
        return tuple( sys.version_info[ :2 ] )


class Check( object ):
    "Result of a single check"

    def __init__( self, name, status, detail, hint=None ):
        self.name = name
        self.status = status
        self.detail = detail
        self.hint = hint

    def asDict( self ):
        "Dictionary form for JSON output"
        return dict( name=self.name, status=self.status,
                     detail=self.detail, hint=self.hint )


def detectEnvironment( env ):
    "Return one of: wsl, container, vm, native, or the OS name"
    if env.system() != 'Linux':
        return env.system().lower() or 'unknown'
    if 'microsoft' in env.read( '/proc/version' ).lower():
        return 'wsl'
    if ( env.exists( '/.dockerenv' ) or env.exists( '/run/.containerenv' )
         or env.read( '/run/systemd/container' ).strip() ):
        return 'container'
    vendor = ( env.read( '/sys/class/dmi/id/sys_vendor' ) + ' ' +
               env.read( '/sys/class/dmi/id/product_name' ) ).lower()
    for hypervisor in ( 'virtualbox', 'vmware', 'qemu', 'kvm', 'parallels',
                        'microsoft corporation', 'xen', 'apple',
                        'amazon ec2', 'google compute engine' ):
        if hypervisor in vendor:
            return 'vm'
    if 'hypervisor' in env.read( '/proc/cpuinfo' ):
        return 'vm'
    return 'native'


def moduleAvailable( env, module ):
    "Is kernel module loaded, built in, or loadable?"
    if env.exists( '/sys/module/%s' % module ):
        return True
    code, _out = env.run( 'modinfo %s' % module )
    return code == 0


def checkBasics( env, add ):
    "Privileges, Python, namespaces and core commands"
    if env.isRoot():
        add( 'root', OK, 'running as root' )
    else:
        add( 'root', WARN, 'not running as root',
             'Mininet must be run with sudo: sudo mn' )
    major, minor = env.pythonVersion()
    if ( major, minor ) >= ( 3, 6 ):
        add( 'python', OK, 'Python %d.%d' % ( major, minor ) )
    else:
        add( 'python', WARN, 'Python %d.%d is unsupported by this fork' %
             ( major, minor ), 'Install and use Python 3' )
    if env.exists( '/proc/self/ns/net' ):
        add( 'netns', OK, 'network namespaces supported' )
    else:
        add( 'netns', FAIL, 'kernel lacks network namespace support',
             'Use a kernel with CONFIG_NET_NS=y (any modern distro)' )
    for cmd, pkg in ( ( 'mnexec', 'Mininet with util/install.sh -n' ),
                      ( 'ip', 'iproute2' ),
                      ( 'ping', 'iputils-ping' ) ):
        if env.which( cmd ):
            add( cmd, OK, 'found %s' % env.which( cmd ) )
        else:
            add( cmd, FAIL, '%s not found' % cmd, 'Install %s' % pkg )


def checkOVS( env, add ):
    "Open vSwitch installation, daemon and datapath; return running?"
    if not env.which( 'ovs-vsctl' ):
        add( 'ovs', WARN, 'Open vSwitch not installed',
             'Install with: util/install.sh -v (or use --switch lxbr)' )
        return False
    code, _out = env.run( 'ovs-vsctl -t 2 show' )
    running = code == 0
    if running:
        add( 'ovs', OK, 'Open vSwitch is running' )
    else:
        add( 'ovs', WARN, 'ovs-vsctl cannot reach ovsdb-server',
             'Start it: sudo service openvswitch-switch start '
             '(or /usr/share/openvswitch/scripts/ovs-ctl start)' )
    if moduleAvailable( env, 'openvswitch' ):
        add( 'ovs-kernel', OK, 'openvswitch kernel datapath available' )
    else:
        add( 'ovs-kernel', INFO, 'no openvswitch kernel module: OVS '
             'switches will use the userspace datapath (slower)',
             'Normal in Docker Desktop and some VMs' )
    return running


def checkController( env, add ):
    "Local OpenFlow controllers; return list of those found"
    controllers = [ c for c in ( 'ovs-testcontroller', 'test-controller',
                                 'ovs-controller', 'controller' )
                    if env.which( c ) ]
    if controllers:
        add( 'controller', OK, 'OpenFlow controller: %s' % controllers[ 0 ] )
    else:
        add( 'controller', WARN, 'no local OpenFlow controller found',
             'Install openvswitch-testcontroller, use a remote controller '
             '(--controller remote), or --switch ovsbr --controller none' )
    return controllers


def checkKernelFeatures( env, add ):
    "Linux bridge and traffic control; return bridge available?"
    bridge = moduleAvailable( env, 'bridge' )
    if not bridge:
        add( 'bridge', WARN, 'Linux bridge not available' )
    elif not env.which( 'brctl' ):
        add( 'bridge', WARN, 'brctl not found: --switch lxbr will not work',
             'Install bridge-utils' )
        bridge = False
    else:
        add( 'bridge', OK, 'Linux bridge available' )
    shaping = [ m for m in ( 'sch_htb', 'sch_netem' )
                if not moduleAvailable( env, m ) ]
    if not env.which( 'tc' ):
        add( 'tc', WARN, 'tc not found: --link tc will not work',
             'Install iproute2' )
    elif shaping:
        add( 'tc', WARN, 'missing qdisc modules: %s' % ' '.join( shaping ),
             '--link tc (bandwidth/delay/loss) may fail on this kernel' )
    else:
        add( 'tc', OK, 'traffic control (htb, netem) available' )
    return bridge


def checkOptional( env, add ):
    "Optional tools and X11"
    missing = [ c for c in ( 'iperf', 'xterm', 'tcpdump' )
                if not env.which( c ) ]
    if missing:
        add( 'optional', INFO, 'optional tools not found: %s' %
             ' '.join( missing ) )
    if not os.environ.get( 'DISPLAY' ):
        add( 'x11', INFO, 'no DISPLAY: xterm and miniedit need an X server',
             'WSLg provides one on Windows 11; use XQuartz on macOS' )


def runChecks( env=None ):
    "Run all checks; return ( environment, checks, suggestion )"
    env = env or Env()
    checks = []

    def add( *args ):
        "Record a check result"
        checks.append( Check( *args ) )

    where = detectEnvironment( env )
    if env.system() != 'Linux':
        add( 'linux', FAIL, 'Mininet requires Linux; this is %s' %
             env.system(),
             'Use Docker (scripts/mininet-docker), WSL2 (Windows) or a '
             'Linux VM - see docs/install/' )
        return where, checks, None
    add( 'linux', OK, 'Linux kernel %s (%s)' % ( platform.release(), where ) )
    checkBasics( env, add )
    ovsRunning = checkOVS( env, add )
    controllers = checkController( env, add )
    bridge = checkKernelFeatures( env, add )
    checkOptional( env, add )
    return where, checks, suggest( ovsRunning, controllers, bridge )


def suggest( ovsRunning, controllers, bridge ):
    "Suggest a command line that should work here"
    if ovsRunning and controllers:
        return 'sudo mn --test pingall'
    if ovsRunning:
        return 'sudo mn --switch ovsbr --controller none --test pingall'
    if bridge:
        return 'sudo mn --switch lxbr --controller none --test pingall'
    return None


SYMBOLS = { OK: '[ ok ]', WARN: '[warn]', FAIL: '[FAIL]', INFO: '[info]' }


def report( where, checks, suggestion, out=sys.stdout ):
    "Print human-readable report; return exit code"
    out.write( 'Mininet doctor (environment: %s)\n\n' % where )
    for check in checks:
        out.write( '%s %-11s %s\n' % ( SYMBOLS[ check.status ], check.name,
                                        check.detail ) )
        if check.hint and check.status != OK:
            out.write( '%s %s\n' % ( ' ' * 19, check.hint ) )
    failed = [ c for c in checks if c.status == FAIL ]
    out.write( '\n' )
    if failed:
        out.write( 'Mininet cannot run here until the failures above '
                   'are fixed.\n' )
    elif suggestion:
        out.write( 'Try: %s\n' % suggestion )
    return 1 if failed else 0


def main( argv=None ):
    "Command-line entry point"
    argv = sys.argv[ 1: ] if argv is None else argv
    if '-h' in argv or '--help' in argv:
        print( __doc__.strip() )
        return 0
    where, checks, suggestion = runChecks()
    if '--json' in argv:
        print( json.dumps( dict(
            environment=where, suggestion=suggestion,
            ok=not any( c.status == FAIL for c in checks ),
            checks=[ c.asDict() for c in checks ] ), indent=2 ) )
        return 0 if all( c.status != FAIL for c in checks ) else 1
    return report( where, checks, suggestion )


if __name__ == '__main__':
    sys.exit( main() )
