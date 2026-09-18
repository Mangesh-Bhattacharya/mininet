"""
Mininet lab configuration files: describe a network once, in the
language you prefer, then check it and run it.

  mn-config init --lang yaml       write a commented starter file
  mn-config validate lab.yaml      check it (no root needed)
  sudo mn-config run lab.yaml      start the network, run tests, open CLI
  mn-config schema                 list every setting and whether
                                   you should edit it

Supported configuration languages:

  YAML (.yaml, .yml) and JSON (.json) files are plain data.

  Python (.py), C (.c), C++ (.cpp), C# (.cs), Java (.java), Ruby (.rb)
  and COBOL (.cob, .cbl) files are small programs that print the same
  configuration as JSON on standard output. mn-config compiles and runs
  them for you (gcc, g++, dotnet, java, ruby or cobc must be installed).
  When started with sudo, these programs run as the user who invoked
  sudo, not as root.

Every language produces the same configuration, which is checked
against one schema (FIELDS below) before anything runs. See
docs/configuration.md for the full reference.
"""

import argparse
import difflib
import io
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from functools import partial

FORMAT_VERSION = 1

# What a user may change. Levels: 'edit' (edit freely), 'care'
# (advanced: change only if you know why) and 'fixed' (do not edit).
EDIT, CARE, FIXED = 'edit', 'care', 'fixed'
LEVELS = { EDIT: 'edit freely', CARE: 'advanced - edit with care',
           FIXED: 'do not edit' }

FIELDS = [
    ( 'version', FIXED, 'Configuration format version. Always 1.' ),
    ( 'name', EDIT, 'Name of your lab, shown in the GUI and logs.' ),
    ( 'description', EDIT, 'Free text describing the lab.' ),
    ( 'network.controller', EDIT,
      'OpenFlow controller: default (built-in test controller), '
      'remote (your own, e.g. Ryu/ONOS/POX) or none.' ),
    ( 'network.controller_ip', EDIT,
      'Address of a remote controller (controller: remote).' ),
    ( 'network.controller_port', EDIT,
      'TCP port of a remote controller (default 6653).' ),
    ( 'network.switch', EDIT,
      'Switch type: ovs (Open vSwitch + controller), ovsbr (Open '
      'vSwitch as a learning bridge), lxbr (Linux bridge) or user.' ),
    ( 'network.datapath', CARE,
      'Open vSwitch datapath: auto, kernel or user. Leave on auto; '
      'Docker Desktop and WSL need user.' ),
    ( 'network.ip_base', CARE,
      'Address range used for hosts without an ip (10.0.0.0/8).' ),
    ( 'network.auto_arp', CARE,
      'Pre-fill ARP tables so the first ping is not lost (true).' ),
    ( 'network.auto_mac', CARE,
      'Give hosts simple MACs like 00:00:00:00:00:01 (true).' ),
    ( 'topology.type', EDIT,
      'Built-in topology: minimal, single, linear or tree. Use this '
      'OR hosts/switches/links, not both.' ),
    ( 'topology.hosts', EDIT,
      'single: number of hosts; linear: hosts per switch.' ),
    ( 'topology.switches', EDIT, 'linear: number of switches.' ),
    ( 'topology.depth', EDIT, 'tree: depth of the tree.' ),
    ( 'topology.fanout', EDIT, 'tree: children per switch.' ),
    ( 'topology.link', EDIT,
      'Link settings applied to every link (bw, delay, loss, '
      'max_queue).' ),
    ( 'hosts[].name', EDIT,
      'Host name: a letter followed by up to 9 letters/digits (h1).' ),
    ( 'hosts[].ip', EDIT, 'IP address with prefix (10.0.0.1/24).' ),
    ( 'hosts[].mac', CARE, 'MAC address (00:00:00:00:00:01).' ),
    ( 'hosts[].gateway', CARE, 'Default gateway IP address.' ),
    ( 'switches[].name', EDIT,
      'Switch name; must contain a number (s1) unless dpid is set.' ),
    ( 'switches[].dpid', CARE,
      'OpenFlow datapath ID, up to 16 hex digits, as a quoted string.' ),
    ( 'switches[].protocols', CARE,
      'OpenFlow versions for ovs switches, e.g. OpenFlow13.' ),
    ( 'links[].from', EDIT, 'Name of the node at one end of the link.' ),
    ( 'links[].to', EDIT, 'Name of the node at the other end.' ),
    ( 'links[].bw', EDIT, 'Bandwidth limit in Mbit/s (0.1 - 1000).' ),
    ( 'links[].delay', EDIT, 'One-way delay, e.g. 5ms, 100us, 1s.' ),
    ( 'links[].loss', EDIT, 'Packet loss in percent (0 - 100).' ),
    ( 'links[].max_queue', CARE, 'Queue size in packets.' ),
    ( 'run[]', EDIT,
      'Commands to run after start: "<node> <command>", e.g. '
      '"h1 python3 -m http.server 80 &".' ),
    ( 'tests[]', EDIT, 'Checks to run after start: pingall, iperf.' ),
    ( 'gui.port', EDIT, 'Port for the web GUI (mn-gui), default 8080.' ),
]

CONTROLLERS = ( 'default', 'remote', 'none' )
SWITCHES = ( 'ovs', 'ovsbr', 'lxbr', 'user' )
DATAPATHS = ( 'auto', 'kernel', 'user' )
TOPOLOGIES = ( 'minimal', 'single', 'linear', 'tree' )
TESTS = ( 'pingall', 'iperf' )
LINK_KEYS = ( 'bw', 'delay', 'loss', 'max_queue' )

DEFAULT_NETWORK = {
    'controller': 'default', 'controller_ip': '127.0.0.1',
    'controller_port': 6653, 'switch': 'ovs', 'datapath': 'auto',
    'ip_base': '10.0.0.0/8', 'auto_arp': True, 'auto_mac': True }

# Interface names are <node>-eth<N> and Linux allows 15 characters
NAME_RE = re.compile( r'^[A-Za-z][A-Za-z0-9]{0,9}$' )
MAC_RE = re.compile( r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$' )
DPID_RE = re.compile( r'^[0-9A-Fa-f]{1,16}$' )
DELAY_RE = re.compile( r'^\d+(\.\d+)?(us|ms|s)$' )
PROTOCOLS_RE = re.compile( r'^OpenFlow1[0-5](,OpenFlow1[0-5])*$' )


class Language( object ):
    "A configuration language and how to turn its files into data"

    def __init__( self, key, title, extensions, tools=() ):
        self.key = key
        self.title = title
        self.extensions = extensions
        self.tools = tools
        self.template = ( 'Lab' if key == 'java' else 'lab' ) + extensions[ 0 ]

    def isData( self ):
        "Is this a data format (rather than a program)?"
        return not self.tools

    def available( self ):
        "Are the tools this language needs installed?"
        return all( shutil.which( tool ) for tool in self.tools )


# Starter templates are templates/lab<first extension> (Lab.java)
LANGUAGES = [
    Language( 'yaml', 'YAML', ( '.yaml', '.yml' ) ),
    Language( 'json', 'JSON', ( '.json', ) ),
    Language( 'python', 'Python', ( '.py', ), ( 'python3', ) ),
    Language( 'c', 'C', ( '.c', ), ( 'gcc', ) ),
    Language( 'cpp', 'C++', ( '.cpp', '.cc', '.cxx' ), ( 'g++', ) ),
    Language( 'csharp', 'C#', ( '.cs', ), ( 'dotnet', ) ),
    Language( 'java', 'Java', ( '.java', ), ( 'java', ) ),
    Language( 'ruby', 'Ruby', ( '.rb', ), ( 'ruby', ) ),
    Language( 'cobol', 'COBOL', ( '.cob', '.cbl' ), ( 'cobc', ) ),
]

TEMPLATE_DIR = os.path.join( os.path.dirname( os.path.abspath(
    __file__ ) ), 'templates' )

BUILD_TIMEOUT = 300
RUN_TIMEOUT = 60


class Issue( object ):
    "A problem found in a configuration"

    def __init__( self, path, message, hint=None ):
        self.path = path
        self.message = message
        self.hint = hint

    def __str__( self ):
        text = '%s: %s' % ( self.path or 'config', self.message )
        if self.hint:
            text += '\n    hint: %s' % self.hint
        return text

    def asDict( self ):
        "JSON-friendly form"
        return { 'path': self.path, 'message': self.message,
                 'hint': self.hint }


class ConfigError( Exception ):
    "A configuration could not be loaded or is invalid"

    def __init__( self, issues ):
        if isinstance( issues, Issue ):
            issues = [ issues ]
        self.issues = issues
        Exception.__init__( self, '\n'.join( str( i ) for i in issues ) )


# Loading

def languageFor( path ):
    "Return the Language for a file name, or raise ConfigError"
    ext = os.path.splitext( path )[ 1 ].lower()
    for lang in LANGUAGES:
        if ext in lang.extensions:
            return lang
    known = ', '.join( e for l in LANGUAGES for e in l.extensions )
    raise ConfigError( Issue( path, 'unknown file type "%s"' % ext,
                              'use one of: %s' % known ) )


def languageByKey( key ):
    "Return the Language called key (yaml, c, cobol...)"
    for lang in LANGUAGES:
        if key.lower() in ( lang.key, lang.title.lower() ):
            return lang
    raise ConfigError( Issue(
        None, 'unknown language "%s"' % key,
        'use one of: %s' % ', '.join( l.key for l in LANGUAGES ) ) )


def parseText( text, fmt='yaml', source='config' ):
    "Parse YAML or JSON text into a Python object"
    if fmt == 'json':
        try:
            return json.loads( text )
        except ValueError as e:
            raise ConfigError( Issue( source,
                                      'invalid JSON: %s' % e ) ) from None
    try:
        import yaml  # pylint: disable=import-outside-toplevel
    except ImportError:
        raise ConfigError( Issue(
            source, 'reading YAML needs the PyYAML package',
            'install python3-yaml (apt) or PyYAML (pip), or use a '
            '.json file' ) ) from None
    try:
        # safe_load: YAML files can't create Python objects
        return yaml.safe_load( text )
    except yaml.YAMLError as e:
        raise ConfigError( Issue( source,
                                  'invalid YAML: %s' % e ) ) from None


def readText( path ):
    "Return the contents of a text file"
    try:
        with io.open( path, encoding='utf-8' ) as f:
            return f.read()
    except ( IOError, OSError ) as e:
        raise ConfigError( Issue( path,
                                  'cannot read file: %s' % e ) ) from None


def load( path ):
    """Load a configuration file in any supported language and
       return the validated configuration (a dict)"""
    lang = languageFor( path )
    if lang.isData():
        data = parseText( readText( path ), lang.key, path )
    else:
        data = runProgram( path, lang )
    return validate( data )


# Running configuration programs

def sudoUser():
    "Return ( uid, gid ) of the user who ran sudo, or None"
    uid, gid = os.environ.get( 'SUDO_UID' ), os.environ.get( 'SUDO_GID' )
    if hasattr( os, 'geteuid' ) and os.geteuid() == 0 and uid and gid:
        if uid.isdigit() and gid.isdigit() and int( uid ) != 0:
            return int( uid ), int( gid )
    return None


def fileOwner():
    """Owner for new files written as root: the user who ran sudo, or
       MININET_OWNER=uid:gid (set by the Docker launchers, so files in
       the mounted workspace belong to you rather than root)"""
    ids = sudoUser()
    if ids:
        return ids
    uid, _, gid = os.environ.get( 'MININET_OWNER', '' ).partition( ':' )
    if uid.isdigit() and gid.isdigit():
        return int( uid ), int( gid )
    return None


def giveToOwner( path ):
    "chown a file we just created to fileOwner(), if running as root"
    owner = fileOwner()
    if owner and hasattr( os, 'geteuid' ) and os.geteuid() == 0:
        try:
            os.chown( path, owner[ 0 ], owner[ 1 ] )
        except OSError:
            pass  # e.g. file systems without Unix ownership


def _programEnv( ids ):
    "Environment for config programs"
    env = dict( os.environ )
    env.update( DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1',
                DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1' )
    if ids:
        import pwd  # pylint: disable=import-outside-toplevel
        try:
            entry = pwd.getpwuid( ids[ 0 ] )
            env.update( HOME=entry.pw_dir, USER=entry.pw_name,
                        LOGNAME=entry.pw_name )
        except KeyError:
            pass
    return env


def _demote( ids ):
    "Return a preexec_fn that drops root privileges to ids"
    def dropPrivileges():
        "Runs in the child before exec"
        os.setgroups( [] )
        os.setgid( ids[ 1 ] )
        os.setuid( ids[ 0 ] )
    return dropPrivileges


def _execute( cmd, cwd, timeout, ids ):
    "Run cmd; return stdout, or raise ConfigError"
    try:
        # cmd is a list and never goes through a shell
        proc = subprocess.run(  # pylint: disable=subprocess-run-check
            cmd, cwd=cwd, env=_programEnv( ids ), timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            preexec_fn=_demote( ids ) if ids else None )
    except OSError as e:
        raise ConfigError( Issue( cmd[ 0 ],
                                  'cannot run: %s' % e ) ) from None
    except subprocess.TimeoutExpired:
        raise ConfigError( Issue(
            cmd[ 0 ], 'timed out after %d seconds' % timeout,
            'make sure the program prints its configuration and '
            'exits' ) ) from None
    if proc.returncode != 0:
        err = proc.stderr.decode( 'utf-8', 'replace' ).strip()
        raise ConfigError( Issue(
            ' '.join( os.path.basename( c ) for c in cmd[ :2 ] ),
            'failed with exit code %d' % proc.returncode,
            err[ -2000: ] or None ) )
    return proc.stdout.decode( 'utf-8', 'replace' )


def _dotnetFramework():
    "Target framework for the installed .NET SDK, e.g. net8.0"
    out = subprocess.run( [ 'dotnet', '--version' ], check=False,
                          stdout=subprocess.PIPE,
                          env=_programEnv( None ) ).stdout
    match = re.match( r'(\d+)\.', out.decode( 'ascii', 'replace' ) )
    return 'net%s.0' % ( match.group( 1 ) if match else '8' )


CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>%s</TargetFramework>
    <AssemblyName>labconfig</AssemblyName>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>disable</Nullable>
  </PropertyGroup>
</Project>
"""


def programCommands( lang, src, workdir ):
    """Return the list of commands that build and run a config
       program; the last command's output is the configuration"""
    exe = os.path.join( workdir, 'labconfig' )
    out = os.path.join( workdir, 'out' )
    commands = {
        'python': [ [ sys.executable or 'python3', src ] ],
        'c': [ [ 'gcc', '-std=c99', '-O1', '-o', exe, src ], [ exe ] ],
        'cpp': [ [ 'g++', '-std=c++17', '-O1', '-o', exe, src ], [ exe ] ],
        'cobol': [ [ 'cobc', '-x', '-free', '-o', exe, src ], [ exe ] ],
        # Java 11+ runs single-file programs directly
        'java': [ [ 'java', src ] ],
        'ruby': [ [ 'ruby', src ] ],
        'csharp': [ [ 'dotnet', 'build', workdir, '-c', 'Release',
                      '-o', out, '--nologo', '-v', 'quiet' ],
                    [ 'dotnet', os.path.join( out, 'labconfig.dll' ) ] ] }
    if lang.key not in commands:
        raise ConfigError( Issue( src, '%s is not a program' %
                                  lang.title ) )
    return commands[ lang.key ]


def runProgram( path, lang ):
    """Build and run a configuration program; parse the JSON it prints.
       When running under sudo, the program runs as the invoking user."""
    missing = [ t for t in lang.tools if not shutil.which( t ) ]
    if missing:
        raise ConfigError( Issue(
            path, '%s configs need %s, which is not installed' %
            ( lang.title, ', '.join( missing ) ),
            'see "Installing language toolchains" in '
            'docs/configuration.md, or use a YAML config' ) )
    ids = sudoUser()
    workdir = tempfile.mkdtemp( prefix='mn-config-' )
    try:
        # Work on a copy, so the program can't modify the original
        # through relative paths and the user can read it after sudo
        src = os.path.join( workdir, os.path.basename( path ) )
        shutil.copyfile( path, src )
        if lang.key == 'csharp':
            with io.open( os.path.join( workdir, 'labconfig.csproj' ),
                          'w' ) as f:
                f.write( CSPROJ % _dotnetFramework() )
        if ids:
            for name in [ workdir ] + [ os.path.join( workdir, n )
                                        for n in os.listdir( workdir ) ]:
                os.chown( name, ids[ 0 ], ids[ 1 ] )
        commands = programCommands( lang, src, workdir )
        output = ''
        for i, cmd in enumerate( commands ):
            # Every command but the last one is a compiler
            last = i == len( commands ) - 1
            output = _execute( cmd, workdir,
                               RUN_TIMEOUT if last else BUILD_TIMEOUT, ids )
    finally:
        shutil.rmtree( workdir, ignore_errors=True )
    try:
        return json.loads( output )
    except ValueError as e:
        raise ConfigError( Issue(
            path, 'the program did not print valid JSON (%s)' % e,
            'first output: %r' % output.strip()[ :200 ] ) ) from None


# Validation

class Checker( object ):
    "Validate raw configuration data and fill in defaults"

    def __init__( self ):
        self.issues = []

    def add( self, path, message, hint=None ):
        "Record a problem"
        self.issues.append( Issue( path, message, hint ) )

    def keys( self, data, path, allowed ):
        "Check that data is a mapping with only allowed keys"
        if not isinstance( data, dict ):
            self.add( path, 'must be a mapping (key: value pairs), not %s'
                      % type( data ).__name__ )
            return False
        for key in data:
            if key not in allowed:
                close = difflib.get_close_matches( str( key ), allowed, 1 )
                self.add( '%s.%s' % ( path, key ) if path else str( key ),
                          'unknown setting',
                          'did you mean "%s"?' % close[ 0 ] if close else
                          'allowed here: %s' % ', '.join( allowed ) )
        return True

    def choice( self, value, path, choices ):
        "Check value is one of choices"
        if value not in choices:
            self.add( path, '"%s" is not allowed' % ( value, ),
                      'use one of: %s' % ', '.join( choices ) )

    def boolean( self, value, path ):
        "Check value is true/false"
        if not isinstance( value, bool ):
            self.add( path, 'must be true or false' )

    def number( self, value, path, limits, types=( int, float ) ):
        "Check value is a number in limits ( low, high )"
        if isinstance( value, bool ) or not isinstance( value, types ):
            self.add( path, 'must be a%s number' %
                      ( 'n integer' if types == ( int, ) else '' ) )
        elif not limits[ 0 ] <= value <= limits[ 1 ]:
            self.add( path, 'must be between %s and %s' % limits )

    def integer( self, value, path, limits ):
        "Check value is an integer in limits ( low, high )"
        self.number( value, path, limits, ( int, ) )

    def name( self, value, path ):
        "Check a node name"
        if not isinstance( value, str ) or not NAME_RE.match( value ):
            self.add( path, 'invalid name %r' % ( value, ),
                      'use a letter followed by up to 9 letters or '
                      'digits, e.g. h1 or s1' )
            return False
        return True

    def address( self, value, path, prefix=True ):
        "Check an IP address; return an ipaddress interface or None"
        try:
            if prefix:
                return ipaddress.ip_interface( str( value ) )
            return ipaddress.ip_address( str( value ) )
        except ValueError:
            self.add( path, 'invalid IP address %r' % ( value, ),
                      'e.g. 10.0.0.1/24' if prefix else 'e.g. 10.0.0.254' )
            return None

    def linkOptions( self, link, path ):
        "Check bw/delay/loss/max_queue in a link or topology.link"
        if 'bw' in link:
            self.number( link[ 'bw' ], path + '.bw', ( 0.1, 1000 ) )
        if 'delay' in link and not DELAY_RE.match( str( link[ 'delay' ] ) ):
            self.add( path + '.delay', 'invalid delay %r' %
                      ( link[ 'delay' ], ), 'e.g. 5ms, 100us or 1s' )
        if 'loss' in link:
            self.number( link[ 'loss' ], path + '.loss', ( 0, 100 ) )
        if 'max_queue' in link:
            self.integer( link[ 'max_queue' ], path + '.max_queue',
                          ( 1, 1000000 ) )


def _checkNetwork( chk, data ):
    "Validate the network section; return it with defaults"
    net = dict( DEFAULT_NETWORK )
    if data is None:
        return net
    if not chk.keys( data, 'network', list( DEFAULT_NETWORK ) ):
        return net
    net.update( data )
    chk.choice( net[ 'controller' ], 'network.controller', CONTROLLERS )
    chk.choice( net[ 'switch' ], 'network.switch', SWITCHES )
    chk.choice( net[ 'datapath' ], 'network.datapath', DATAPATHS )
    chk.address( net[ 'controller_ip' ], 'network.controller_ip',
                 prefix=False )
    chk.integer( net[ 'controller_port' ], 'network.controller_port',
                 ( 1, 65535 ) )
    try:
        ipaddress.ip_network( str( net[ 'ip_base' ] ), strict=False )
    except ValueError:
        chk.add( 'network.ip_base', 'invalid network %r' %
                 ( net[ 'ip_base' ], ), 'e.g. 10.0.0.0/8' )
    chk.boolean( net[ 'auto_arp' ], 'network.auto_arp' )
    chk.boolean( net[ 'auto_mac' ], 'network.auto_mac' )
    if net[ 'controller' ] == 'none' and net[ 'switch' ] in ( 'ovs',
                                                              'user' ):
        chk.add( 'network.controller',
                 'switch "%s" needs a controller to forward packets'
                 % net[ 'switch' ],
                 'use switch: ovsbr or lxbr with controller: none' )
    return net


TOPOLOGY_PARAMS = {
    'minimal': (), 'single': ( 'hosts', ),
    'linear': ( 'switches', 'hosts' ), 'tree': ( 'depth', 'fanout' ) }


def _checkTopology( chk, data ):
    "Validate a built-in topology section"
    allowed = [ 'type', 'hosts', 'switches', 'depth', 'fanout', 'link' ]
    if not chk.keys( data, 'topology', allowed ):
        return None
    topo = dict( data )
    chk.choice( topo.get( 'type' ), 'topology.type', TOPOLOGIES )
    params = TOPOLOGY_PARAMS.get( topo.get( 'type' ), () )
    for key in ( 'hosts', 'switches', 'depth', 'fanout' ):
        if key not in topo:
            continue
        if key not in params:
            chk.add( 'topology.' + key, 'not used by topology type "%s"' %
                     topo.get( 'type' ),
                     'settings for this type: %s' %
                     ( ', '.join( params ) or 'none' ) )
        else:
            chk.integer( topo[ key ], 'topology.' + key, ( 1, 64 ) )
    if 'link' in topo:
        if chk.keys( topo[ 'link' ], 'topology.link', list( LINK_KEYS ) ):
            chk.linkOptions( topo[ 'link' ], 'topology.link' )
    return topo


def _checkHosts( chk, hosts, names, ips ):
    "Validate the hosts list"
    for i, host in enumerate( hosts ):
        path = 'hosts[%d]' % i
        if not chk.keys( host, path, [ 'name', 'ip', 'mac', 'gateway' ] ):
            continue
        name = host.get( 'name' )
        if chk.name( name, path + '.name' ):
            path = 'hosts.%s' % name
            if name in names:
                chk.add( path, 'name "%s" is used twice' % name )
            names.add( name )
        if 'ip' in host:
            intf = chk.address( host[ 'ip' ], path + '.ip' )
            if intf and intf.ip in ips:
                chk.add( path + '.ip', 'address %s is used twice' %
                         intf.ip )
            elif intf:
                ips.add( intf.ip )
        if 'mac' in host and not MAC_RE.match( str( host[ 'mac' ] ) ):
            chk.add( path + '.mac', 'invalid MAC %r' % ( host[ 'mac' ], ),
                     'e.g. 00:00:00:00:00:01' )
        if 'gateway' in host:
            chk.address( host[ 'gateway' ], path + '.gateway',
                         prefix=False )


def _checkSwitches( chk, switches, names ):
    "Validate the switches list"
    for i, switch in enumerate( switches ):
        path = 'switches[%d]' % i
        if not chk.keys( switch, path, [ 'name', 'dpid', 'protocols' ] ):
            continue
        name = switch.get( 'name' )
        if chk.name( name, path + '.name' ):
            path = 'switches.%s' % name
            if name in names:
                chk.add( path, 'name "%s" is used twice' % name )
            names.add( name )
            if 'dpid' not in switch and not re.search( r'\d', name ):
                chk.add( path + '.name', 'no number in switch name',
                         'Mininet derives the datapath ID from the number:'
                         ' rename it (e.g. s1) or set a dpid' )
        dpid = switch.get( 'dpid' )
        if dpid is not None and not ( isinstance( dpid, str ) and
                                      DPID_RE.match( dpid ) ):
            chk.add( path + '.dpid', 'must be up to 16 hex digits, quoted',
                     'e.g. dpid: "0000000000000001" (quotes stop YAML '
                     'reading it as a number)' )
        protocols = switch.get( 'protocols' )
        if protocols is not None and not PROTOCOLS_RE.match(
                str( protocols ) ):
            chk.add( path + '.protocols', 'invalid %r' % ( protocols, ),
                     'e.g. OpenFlow13 or OpenFlow10,OpenFlow13' )


def _checkLinks( chk, links, names ):
    "Validate links; accepts [a, b] or {from: a, to: b, ...}"
    result = []
    for i, link in enumerate( links ):
        path = 'links[%d]' % i
        if isinstance( link, list ) and len( link ) == 2:
            link = { 'from': link[ 0 ], 'to': link[ 1 ] }
        if not chk.keys( link, path, [ 'from', 'to' ] + list( LINK_KEYS ) ):
            continue
        for end in ( 'from', 'to' ):
            if link.get( end ) not in names:
                chk.add( '%s.%s' % ( path, end ),
                         'unknown node %r' % ( link.get( end ), ),
                         'define it under hosts or switches first' )
        if link.get( 'from' ) == link.get( 'to' ):
            chk.add( path, 'a link needs two different nodes' )
        chk.linkOptions( link, path )
        result.append( link )
    return result


def _checkList( chk, data, key ):
    "Return data[key] if it is a list (or missing), else report it"
    value = data.get( key )
    if value is None:
        return []
    if not isinstance( value, list ):
        chk.add( key, 'must be a list' )
        return []
    return value


def _checkRun( chk, commands, names ):
    "Validate run commands: '<node> <command>'"
    for i, command in enumerate( commands ):
        path = 'run[%d]' % i
        if not isinstance( command, str ) or ' ' not in command.strip():
            chk.add( path, 'must be "<node> <command>"',
                     'e.g. "h1 ping -c1 h2"' )
            continue
        node = command.split()[ 0 ]
        if node not in names:
            chk.add( path, 'unknown node "%s"' % node,
                     'nodes: %s' % ', '.join( sorted( names ) ) )


def validate( data ):
    """Validate configuration data from any language.
       Returns the normalized configuration or raises ConfigError."""
    chk = Checker()
    if data is None:
        data = {}
    allowed = [ 'version', 'name', 'description', 'network', 'topology',
                'hosts', 'switches', 'links', 'run', 'tests', 'gui' ]
    if not chk.keys( data, '', allowed ):
        raise ConfigError( chk.issues )
    if data.get( 'version', FORMAT_VERSION ) != FORMAT_VERSION:
        chk.add( 'version', 'unsupported version %r' %
                 ( data.get( 'version' ), ), 'set version: 1' )
    cfg = { 'version': FORMAT_VERSION,
            'name': str( data.get( 'name' ) or 'mininet-lab' ),
            'description': str( data.get( 'description' ) or '' ),
            'network': _checkNetwork( chk, data.get( 'network' ) ),
            'topology': None, 'hosts': [], 'switches': [], 'links': [] }
    explicit = [ k for k in ( 'hosts', 'switches', 'links' ) if k in data ]
    if 'topology' in data and explicit:
        chk.add( 'topology', 'use either topology or %s, not both' %
                 '/'.join( explicit ),
                 'remove the topology section to define nodes yourself' )
    elif 'topology' in data:
        cfg[ 'topology' ] = _checkTopology( chk, data[ 'topology' ] )
    elif not explicit:
        cfg[ 'topology' ] = { 'type': 'minimal' }
    names, ips = set(), set()
    cfg[ 'hosts' ] = _checkList( chk, data, 'hosts' )
    cfg[ 'switches' ] = _checkList( chk, data, 'switches' )
    _checkHosts( chk, cfg[ 'hosts' ], names, ips )
    _checkSwitches( chk, cfg[ 'switches' ], names )
    cfg[ 'links' ] = _checkLinks( chk, _checkList( chk, data, 'links' ),
                                  names )
    cfg[ 'tests' ] = _checkList( chk, data, 'tests' )
    for i, test in enumerate( cfg[ 'tests' ] ):
        chk.choice( test, 'tests[%d]' % i, TESTS )
    gui = data.get( 'gui' ) or {}
    cfg[ 'gui' ] = { 'port': 8080 }
    if chk.keys( gui, 'gui', [ 'port' ] ) and 'port' in gui:
        chk.integer( gui[ 'port' ], 'gui.port', ( 1, 65535 ) )
        cfg[ 'gui' ][ 'port' ] = gui[ 'port' ]
    cfg[ 'run' ] = _checkList( chk, data, 'run' )
    if not chk.issues:
        topo = buildTopo( cfg )
        _checkRun( chk, cfg[ 'run' ], set( topo.nodes() ) )
    if chk.issues:
        raise ConfigError( chk.issues )
    return cfg


# Building networks

def _linkParams( options ):
    "Convert config link options to TCLink parameters"
    params = {}
    for key in ( 'bw', 'delay', 'loss' ):
        if key in options:
            params[ key ] = options[ key ]
    if 'max_queue' in options:
        params[ 'max_queue_size' ] = options[ 'max_queue' ]
    return params


def buildTopo( cfg ):
    "Return a mininet Topo for a validated configuration"
    # Imported here so validation works without Mininet's Linux deps
    # pylint: disable=import-outside-toplevel
    from mininet.topo import ( Topo, MinimalTopo, SingleSwitchTopo,
                               LinearTopo )
    from mininet.topolib import TreeTopo
    topo = cfg.get( 'topology' )
    if topo:
        lopts = _linkParams( topo.get( 'link', {} ) )
        kind = topo[ 'type' ]
        if kind == 'single':
            return SingleSwitchTopo( k=topo.get( 'hosts', 2 ), lopts=lopts )
        if kind == 'linear':
            return LinearTopo( k=topo.get( 'switches', 2 ),
                               n=topo.get( 'hosts', 1 ), lopts=lopts )
        if kind == 'tree':
            return TreeTopo( depth=topo.get( 'depth', 2 ),
                             fanout=topo.get( 'fanout', 2 ), lopts=lopts )
        return MinimalTopo( lopts=lopts )
    result = Topo()
    for host in cfg[ 'hosts' ]:
        opts = {}
        if 'ip' in host:
            opts[ 'ip' ] = str( host[ 'ip' ] )
        if 'mac' in host:
            opts[ 'mac' ] = host[ 'mac' ]
        if 'gateway' in host:
            opts[ 'defaultRoute' ] = 'via %s' % host[ 'gateway' ]
        result.addHost( host[ 'name' ], **opts )
    for switch in cfg[ 'switches' ]:
        opts = { k: switch[ k ] for k in ( 'dpid', 'protocols' )
                 if k in switch }
        result.addSwitch( switch[ 'name' ], **opts )
    for link in cfg[ 'links' ]:
        result.addLink( link[ 'from' ], link[ 'to' ], **_linkParams( link ) )
    return result


def usesShaping( cfg ):
    "Does any link need traffic control (bw/delay/loss)?"
    links = list( cfg[ 'links' ] )
    if cfg.get( 'topology' ):
        links.append( cfg[ 'topology' ].get( 'link', {} ) )
    return any( k in link for link in links for k in LINK_KEYS )


def netParams( cfg ):
    "Return keyword arguments for Mininet() from a validated config"
    # pylint: disable=import-outside-toplevel
    from mininet.node import ( OVSSwitch, OVSBridge, UserSwitch,
                               DefaultController, RemoteController )
    from mininet.nodelib import LinuxBridge
    from mininet.link import Link, TCLink
    net = cfg[ 'network' ]
    switch = { 'ovs': OVSSwitch, 'ovsbr': OVSBridge, 'lxbr': LinuxBridge,
               'user': UserSwitch }[ net[ 'switch' ] ]
    if net[ 'switch' ] in ( 'ovs', 'ovsbr' ) and net[ 'datapath' ] != 'auto':
        switch = partial( switch, datapath=net[ 'datapath' ] )
    controller = { 'default': DefaultController, 'none': None,
                   'remote': partial( RemoteController,
                                      ip=net[ 'controller_ip' ],
                                      port=net[ 'controller_port' ] )
                   }[ net[ 'controller' ] ]
    return dict( topo=buildTopo( cfg ), switch=switch,
                 controller=controller,
                 link=TCLink if usesShaping( cfg ) else Link,
                 ipBase=net[ 'ip_base' ], autoSetMacs=net[ 'auto_mac' ],
                 autoStaticArp=net[ 'auto_arp' ],
                 waitConnected=net[ 'controller' ] != 'none' )


def buildNet( cfg ):
    "Return a (not yet started) Mininet for a validated configuration"
    from mininet.net import Mininet  # pylint: disable=import-outside-toplevel
    return Mininet( **netParams( cfg ) )


def runCommands( net, cfg ):
    "Run the configuration's startup commands; return their output"
    outputs = []
    for command in cfg[ 'run' ]:
        node, _, rest = command.strip().partition( ' ' )
        outputs.append( ( command, net[ node ].cmd( rest ) ) )
    return outputs


def runTests( net, cfg ):
    "Run the configuration's tests; return the number that failed"
    failed = 0
    for test in cfg[ 'tests' ]:
        if test == 'pingall':
            failed += net.pingAll() > 0
        elif test == 'iperf' and len( net.hosts ) >= 2:
            try:
                net.iperf( seconds=3 )
            except Exception:  # pylint: disable=broad-except
                failed += 1
    return failed


def graph( cfg ):
    "Nodes and links of a validated configuration, for drawing"
    topo = buildTopo( cfg )
    nodes = [ { 'id': h, 'kind': 'host' } for h in topo.hosts() ]
    nodes += [ { 'id': s, 'kind': 'switch' } for s in topo.switches() ]
    links = []
    for src, dst, info in topo.links( sort=True, withInfo=True ):
        label = []
        if 'bw' in info:
            label.append( '%sMb/s' % info[ 'bw' ] )
        if 'delay' in info:
            label.append( str( info[ 'delay' ] ) )
        if 'loss' in info:
            label.append( '%s%% loss' % info[ 'loss' ] )
        links.append( { 'from': src, 'to': dst,
                        'label': ' '.join( label ) } )
    if cfg[ 'network' ][ 'controller' ] != 'none' and topo.switches():
        nodes.append( { 'id': 'c0', 'kind': 'controller' } )
        links += [ { 'from': 'c0', 'to': s, 'label': '', 'control': True }
                   for s in topo.switches() ]
    return { 'nodes': nodes, 'links': links }


def summary( cfg ):
    "One-paragraph description of a validated configuration"
    topo = buildTopo( cfg )
    net = cfg[ 'network' ]
    lines = [ '%s: %d hosts, %d switches, %d links' % (
        cfg[ 'name' ], len( topo.hosts() ), len( topo.switches() ),
        len( topo.links() ) ),
        'switch=%s controller=%s datapath=%s' % (
            net[ 'switch' ], net[ 'controller' ], net[ 'datapath' ] ) ]
    if usesShaping( cfg ):
        lines.append( 'link shaping (bw/delay/loss) is enabled' )
    return '\n'.join( lines )


# Templates

def templatePath( lang ):
    "Path of the starter template for a language"
    return os.path.join( TEMPLATE_DIR, lang.template )


def writeTemplate( lang, dest=None, force=False ):
    "Copy the starter template for lang to dest; return dest"
    dest = dest or lang.template
    if os.path.exists( dest ) and not force:
        raise ConfigError( Issue( dest, 'file already exists',
                                  'choose another name or use --force' ) )
    shutil.copyfile( templatePath( lang ), dest )
    giveToOwner( dest )
    return dest


def schemaText():
    "Human-readable reference of every setting"
    lines = [ 'Mininet lab configuration settings (format version %d)'
              % FORMAT_VERSION, '' ]
    for level in ( EDIT, CARE, FIXED ):
        lines.append( '%s:' % LEVELS[ level ].upper() )
        for path, lvl, text in FIELDS:
            if lvl == level:
                lines += textwrap.wrap(
                    text, 79, initial_indent='  %-24s ' % path,
                    subsequent_indent=' ' * 27 )
        lines.append( '' )
    return '\n'.join( lines )


# Command line

def _cmdInit( args ):
    "mn-config init"
    lang = languageByKey( args.lang )
    dest = writeTemplate( lang, args.output, args.force )
    print( 'Wrote %s (%s). Edit it, then run:' % ( dest, lang.title ) )
    print( '  mn-config validate %s' % dest )
    print( '  sudo mn-config run %s' % dest )
    return 0


def _cmdValidate( args ):
    "mn-config validate"
    cfg = load( args.file )
    print( 'OK  %s' % args.file )
    print( summary( cfg ) )
    return 0


def _cmdShow( args ):
    "mn-config show"
    print( json.dumps( load( args.file ), indent=2, sort_keys=True ) )
    return 0


def _cmdRun( args ):
    "mn-config run"
    cfg = load( args.file )
    if not hasattr( os, 'geteuid' ) or os.geteuid() != 0:
        print( 'mn-config run needs root: sudo mn-config run %s' %
               args.file, file=sys.stderr )
        return 1
    # pylint: disable=import-outside-toplevel
    from mininet.log import setLogLevel, info
    from mininet.cli import CLI
    setLogLevel( args.verbosity )
    info( '*** %s\n' % summary( cfg ).replace( '\n', '\n*** ' ) )
    net = buildNet( cfg )
    failed = 0
    try:
        net.start()
        for command, out in runCommands( net, cfg ):
            info( '*** %s\n%s' % ( command, out ) )
        failed = runTests( net, cfg )
        if not args.no_cli:
            CLI( net )
    finally:
        net.stop()
    return 1 if failed else 0


def _cmdLanguages( _args ):
    "mn-config languages"
    for lang in LANGUAGES:
        tools = ', '.join( lang.tools ) or '-'
        state = 'ready' if lang.available() else 'install ' + tools
        print( '%-8s %-7s %-18s %s' % (
            lang.key, lang.title, ' '.join( lang.extensions ), state ) )
    return 0


def _cmdSchema( _args ):
    "mn-config schema"
    print( schemaText() )
    return 0


def parser():
    "Argument parser for mn-config"
    p = argparse.ArgumentParser(
        prog='mn-config',
        description='Create, check and run Mininet lab configurations '
        'written in YAML, JSON, Python, C, C++, C#, Java, Ruby or COBOL.' )
    sub = p.add_subparsers( dest='command' )
    sub.required = True
    s = sub.add_parser( 'init', help='write a commented starter config' )
    s.add_argument( '--lang', '-l', default='yaml',
                    help='yaml, json, python, c, cpp, csharp, java, ruby '
                    'or cobol (default: yaml)' )
    s.add_argument( '--output', '-o', help='file to write' )
    s.add_argument( '--force', action='store_true',
                    help='overwrite an existing file' )
    s.set_defaults( func=_cmdInit )
    for name, func, text in (
            ( 'validate', _cmdValidate, 'check a config (no root needed)' ),
            ( 'show', _cmdShow, 'print the normalized config as JSON' ),
            ( 'run', _cmdRun, 'start the network (needs root)' ) ):
        s = sub.add_parser( name, help=text )
        s.add_argument( 'file' )
        s.set_defaults( func=func )
    s.add_argument( '--no-cli', action='store_true',
                    help='exit after startup commands and tests' )
    s.add_argument( '--verbosity', '-v', default='info',
                    help='log level: info, output, warning, debug' )
    sub.add_parser( 'languages', help='list languages and whether their '
                    'tools are installed' ).set_defaults( func=_cmdLanguages )
    sub.add_parser( 'schema', help='list every setting and whether to '
                    'edit it' ).set_defaults( func=_cmdSchema )
    return p


def main( argv=None ):
    "Entry point for mn-config"
    args = parser().parse_args( argv )
    try:
        return args.func( args )
    except ConfigError as e:
        print( 'Configuration problem%s:' % (
            's' if len( e.issues ) > 1 else '' ), file=sys.stderr )
        for issue in e.issues:
            print( '  - %s' % issue, file=sys.stderr )
        return 2


if __name__ == '__main__':
    sys.exit( main() )
