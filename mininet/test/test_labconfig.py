#!/usr/bin/env python3

"""
Unit tests for mininet.labconfig (lab configuration files).
These don't need root or Open vSwitch:

  python3 -m unittest mininet.test.test_labconfig -v
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from mininet import labconfig
from mininet.labconfig import ConfigError, validate


def paths( error ):
    "Issue paths of a ConfigError"
    return [ i.path for i in error.issues ]


class TemplateTests( unittest.TestCase ):
    "Every starter template produces the same valid lab"

    def setUp( self ):
        self.tmp = tempfile.mkdtemp()

    def tearDown( self ):
        shutil.rmtree( self.tmp )

    def checkTemplate( self, key ):
        "Write the template for key, load it and check the lab"
        lang = labconfig.languageByKey( key )
        dest = os.path.join( self.tmp, lang.template )
        labconfig.writeTemplate( lang, dest )
        cfg = labconfig.load( dest )
        self.assertEqual( cfg[ 'name' ], 'two-switch-lab' )
        topo = labconfig.buildTopo( cfg )
        self.assertEqual( sorted( topo.hosts() ), [ 'h1', 'h2', 'h3' ] )
        self.assertEqual( sorted( topo.switches() ), [ 's1', 's2' ] )
        self.assertEqual( len( topo.links() ), 4 )
        self.assertTrue( labconfig.usesShaping( cfg ) )
        self.assertEqual( cfg[ 'tests' ], [ 'pingall' ] )

    def testDataTemplates( self ):
        "YAML and JSON"
        for key in ( 'yaml', 'json' ):
            with self.subTest( lang=key ):
                self.checkTemplate( key )

    def testProgramTemplates( self ):
        "Python, C, C++, C#, Java, Ruby, COBOL (if their tools exist)"
        for key in ( 'python', 'c', 'cpp', 'csharp', 'java', 'ruby',
                     'cobol' ):
            lang = labconfig.languageByKey( key )
            with self.subTest( lang=key ):
                if not lang.available() and key != 'python':
                    self.skipTest( '%s not installed' % lang.tools[ 0 ] )
                self.checkTemplate( key )

    def testEveryLanguageHasATemplate( self ):
        "Template files exist for all languages"
        for lang in labconfig.LANGUAGES:
            self.assertTrue( os.path.exists( labconfig.templatePath( lang ) ),
                             lang.template )

    def testInitRefusesToOverwrite( self ):
        "init doesn't clobber an existing file unless forced"
        dest = os.path.join( self.tmp, 'lab.yaml' )
        with redirect_stdout( io.StringIO() ):
            self.assertEqual( labconfig.main(
                [ 'init', '-o', dest ] ), 0 )
        with redirect_stderr( io.StringIO() ):
            self.assertEqual( labconfig.main(
                [ 'init', '-o', dest ] ), 2 )
        with redirect_stdout( io.StringIO() ):
            self.assertEqual( labconfig.main(
                [ 'init', '-o', dest, '--force' ] ), 0 )


class ValidationTests( unittest.TestCase ):
    "Checks and friendly messages"

    def assertInvalid( self, data, path ):
        "data must be rejected with an issue at path"
        with self.assertRaises( ConfigError ) as ctx:
            validate( data )
        self.assertIn( path, paths( ctx.exception ) )
        return ctx.exception

    def testEmptyConfigIsMinimal( self ):
        "An empty config is the default two-host network"
        cfg = validate( {} )
        self.assertEqual( cfg[ 'topology' ], { 'type': 'minimal' } )
        topo = labconfig.buildTopo( cfg )
        self.assertEqual( len( topo.hosts() ), 2 )

    def testBuiltInTopologies( self ):
        "single, linear, tree"
        cases = [ ( { 'type': 'single', 'hosts': 4 }, 4, 1 ),
                  ( { 'type': 'linear', 'switches': 3, 'hosts': 2 }, 6, 3 ),
                  ( { 'type': 'tree', 'depth': 2, 'fanout': 3 }, 9, 4 ) ]
        for topology, hosts, switches in cases:
            topo = labconfig.buildTopo( validate( { 'topology': topology } ) )
            self.assertEqual( len( topo.hosts() ), hosts )
            self.assertEqual( len( topo.switches() ), switches )

    def testTopologyLinkOptions( self ):
        "topology.link shapes every link"
        cfg = validate( { 'topology': { 'type': 'single', 'hosts': 2,
                                        'link': { 'bw': 5 } } } )
        topo = labconfig.buildTopo( cfg )
        for _src, _dst, info in topo.links( withInfo=True ):
            self.assertEqual( info[ 'bw' ], 5 )

    def testUnknownKeySuggestion( self ):
        "Typos get a did-you-mean hint"
        err = self.assertInvalid( { 'netwrok': {} }, 'netwrok' )
        self.assertIn( '"network"', err.issues[ 0 ].hint )

    def testParameterForWrongTopology( self ):
        "fanout means nothing to single"
        self.assertInvalid( { 'topology': { 'type': 'single',
                                            'fanout': 2 } },
                            'topology.fanout' )

    def testTopologyAndNodesConflict( self ):
        "Either a built-in topology or explicit nodes"
        self.assertInvalid( { 'topology': { 'type': 'minimal' },
                              'hosts': [ { 'name': 'h1' } ] }, 'topology' )

    def testNames( self ):
        "Bad and duplicate names"
        self.assertInvalid( { 'hosts': [ { 'name': 'host-number-1' } ] },
                            'hosts[0].name' )
        self.assertInvalid( { 'hosts': [ { 'name': 'h1' } ],
                              'switches': [ { 'name': 'h1' } ] },
                            'switches.h1' )

    def testSwitchNeedsNumberOrDpid( self ):
        "Mininet derives dpids from switch names"
        self.assertInvalid( { 'switches': [ { 'name': 'core' } ] },
                            'switches.core.name' )
        cfg = validate( { 'switches': [ { 'name': 'core',
                                          'dpid': '0a' } ] } )
        self.assertEqual( cfg[ 'switches' ][ 0 ][ 'dpid' ], '0a' )

    def testUnquotedDpid( self ):
        "YAML turns unquoted dpids into numbers"
        self.assertInvalid( { 'switches': [ { 'name': 's1', 'dpid': 10 } ] },
                            'switches.s1.dpid' )

    def testAddresses( self ):
        "IP addresses, duplicates, MACs"
        self.assertInvalid( { 'hosts': [ { 'name': 'h1',
                                           'ip': '10.0.0.300/24' } ] },
                            'hosts.h1.ip' )
        self.assertInvalid( { 'hosts': [ { 'name': 'h1', 'ip': '10.0.0.1' },
                                         { 'name': 'h2',
                                           'ip': '10.0.0.1/24' } ] },
                            'hosts.h2.ip' )
        self.assertInvalid( { 'hosts': [ { 'name': 'h1', 'mac': 'zz' } ] },
                            'hosts.h1.mac' )

    def testLinks( self ):
        "Link ends and shaping values"
        base = { 'hosts': [ { 'name': 'h1' } ],
                 'switches': [ { 'name': 's1' } ] }
        self.assertInvalid( dict( base, links=[ [ 'h1', 's9' ] ] ),
                            'links[0].to' )
        self.assertInvalid( dict( base, links=[ [ 's1', 's1' ] ] ),
                            'links[0]' )
        for key, value in ( ( 'bw', 0 ), ( 'bw', 'fast' ),
                            ( 'delay', 5 ), ( 'loss', 101 ),
                            ( 'max_queue', 1.5 ) ):
            link = { 'from': 'h1', 'to': 's1', key: value }
            self.assertInvalid( dict( base, links=[ link ] ),
                                'links[0].%s' % key )

    def testControllerNeededByOvs( self ):
        "controller: none only works with bridges"
        self.assertInvalid( { 'network': { 'controller': 'none' } },
                            'network.controller' )
        validate( { 'network': { 'controller': 'none',
                                 'switch': 'lxbr' } } )

    def testNetworkChoices( self ):
        "Enumerated network settings"
        for key, value in ( ( 'switch', 'cisco' ), ( 'datapath', 'fast' ),
                            ( 'controller_port', 70000 ),
                            ( 'controller_ip', 'nowhere' ),
                            ( 'auto_arp', 'yes' ),
                            ( 'ip_base', '10.0.0/8' ) ):
            self.assertInvalid( { 'network': { key: value } },
                                'network.%s' % key )

    def testRunCommandsNeedKnownNodes( self ):
        "run: '<node> <command>'"
        self.assertInvalid( { 'run': [ 'h9 ping -c1 h1' ] }, 'run[0]' )
        self.assertInvalid( { 'run': [ 'h1' ] }, 'run[0]' )
        validate( { 'run': [ 'h1 ping -c1 h2' ] } )

    def testTestsAndGui( self ):
        "tests and gui.port"
        self.assertInvalid( { 'tests': [ 'pingal' ] }, 'tests[0]' )
        self.assertInvalid( { 'gui': { 'port': 0 } }, 'gui.port' )
        self.assertEqual( validate( { 'gui': { 'port': 9000 } } )[ 'gui' ],
                          { 'port': 9000 } )

    def testVersion( self ):
        "Only version 1 exists"
        self.assertInvalid( { 'version': 2 }, 'version' )

    def testNotAMapping( self ):
        "Top level must be a mapping"
        self.assertInvalid( [ 1, 2 ], '' )


class BuildTests( unittest.TestCase ):
    "Configurations map onto Mininet classes"

    def testNetParams( self ):
        "Switch, controller, link classes"
        # pylint: disable=import-outside-toplevel
        from mininet.link import Link, TCLink
        from mininet.nodelib import LinuxBridge
        params = labconfig.netParams( validate( {} ) )
        self.assertIs( params[ 'link' ], Link )
        self.assertTrue( params[ 'waitConnected' ] )
        params = labconfig.netParams( validate( {
            'network': { 'controller': 'none', 'switch': 'lxbr' },
            'topology': { 'type': 'minimal', 'link': { 'delay': '1ms' } }
        } ) )
        self.assertIsNone( params[ 'controller' ] )
        self.assertIs( params[ 'switch' ], LinuxBridge )
        self.assertIs( params[ 'link' ], TCLink )
        self.assertFalse( params[ 'waitConnected' ] )

    def testRemoteControllerAndDatapath( self ):
        "Partial constructors carry settings"
        params = labconfig.netParams( validate( { 'network': {
            'controller': 'remote', 'controller_ip': '192.0.2.10',
            'controller_port': 6633, 'datapath': 'user' } } ) )
        self.assertEqual( params[ 'controller' ].keywords,
                          { 'ip': '192.0.2.10', 'port': 6633 } )
        self.assertEqual( params[ 'switch' ].keywords,
                          { 'datapath': 'user' } )

    def testHostOptions( self ):
        "ip, mac and gateway reach the topology"
        cfg = validate( { 'hosts': [ { 'name': 'h1', 'ip': '10.1.0.1/16',
                                       'mac': '00:00:00:00:00:0a',
                                       'gateway': '10.1.0.254' } ] } )
        info = labconfig.buildTopo( cfg ).nodeInfo( 'h1' )
        self.assertEqual( info[ 'ip' ], '10.1.0.1/16' )
        self.assertEqual( info[ 'mac' ], '00:00:00:00:00:0a' )
        self.assertEqual( info[ 'defaultRoute' ], 'via 10.1.0.254' )

    def testGraph( self ):
        "Graph for the GUI"
        cfg = validate( { 'hosts': [ { 'name': 'h1' } ],
                          'switches': [ { 'name': 's1' } ],
                          'links': [ { 'from': 'h1', 'to': 's1', 'bw': 10,
                                       'delay': '5ms', 'loss': 1 } ] } )
        graph = labconfig.graph( cfg )
        kinds = { n[ 'id' ]: n[ 'kind' ] for n in graph[ 'nodes' ] }
        self.assertEqual( kinds, { 'h1': 'host', 's1': 'switch',
                                   'c0': 'controller' } )
        labels = [ l[ 'label' ] for l in graph[ 'links' ] ]
        self.assertIn( '10Mb/s 5ms 1% loss', labels )


class ProgramTests( unittest.TestCase ):
    "Configuration programs"

    def setUp( self ):
        self.tmp = tempfile.mkdtemp()

    def tearDown( self ):
        shutil.rmtree( self.tmp )

    def program( self, source ):
        "Write a Python config program"
        path = os.path.join( self.tmp, 'cfg.py' )
        with io.open( path, 'w' ) as f:
            f.write( source )
        return path

    def testPrintsJson( self ):
        "A program's JSON output is validated"
        path = self.program(
            'import json\nprint(json.dumps('
            '{"topology": {"type": "single", "hosts": 3}}))\n' )
        topo = labconfig.buildTopo( labconfig.load( path ) )
        self.assertEqual( len( topo.hosts() ), 3 )

    def testNotJson( self ):
        "Garbage output is explained"
        with self.assertRaises( ConfigError ) as ctx:
            labconfig.load( self.program( 'print("hello")\n' ) )
        self.assertIn( 'valid JSON', str( ctx.exception ) )

    def testFailure( self ):
        "A crashing program shows its error output"
        with self.assertRaises( ConfigError ) as ctx:
            labconfig.load( self.program( 'raise SystemExit("boom")\n' ) )
        self.assertIn( 'boom', ctx.exception.issues[ 0 ].hint )

    def testRunsOnACopy( self ):
        "Programs run in a scratch directory"
        path = self.program( 'import os, json\nopen("junk", "w").close()\n'
                             'print(json.dumps({}))\n' )
        labconfig.load( path )
        self.assertEqual( os.listdir( self.tmp ), [ 'cfg.py' ] )

    def testMissingTool( self ):
        "Missing compilers are reported, not crashed on"
        lang = labconfig.Language( 'x', 'X', ( '.x', ),
                                   ( 'no-such-compiler-mn', ) )
        with self.assertRaises( ConfigError ) as ctx:
            labconfig.runProgram( 'lab.x', lang )
        self.assertIn( 'not installed', str( ctx.exception ) )

    def testUnknownExtension( self ):
        "Unknown file types"
        with self.assertRaises( ConfigError ):
            labconfig.languageFor( 'lab.txt' )

    def testNoPrivilegeDropWithoutSudo( self ):
        "Only root started through sudo drops privileges"
        env = dict( os.environ )
        try:
            os.environ[ 'SUDO_UID' ] = '1000'
            os.environ[ 'SUDO_GID' ] = '1000'
            expected = ( 1000, 1000 ) if os.geteuid() == 0 else None
            self.assertEqual( labconfig.sudoUser(), expected )
        finally:
            os.environ.clear()
            os.environ.update( env )


class CommandLineTests( unittest.TestCase ):
    "mn-config commands that don't need root"

    def mnconfig( self, *args ):
        "Run mn-config; return ( exit code, stdout, stderr )"
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout( out ), redirect_stderr( err ):
            code = labconfig.main( list( args ) )
        return code, out.getvalue(), err.getvalue()

    def testShowAndValidate( self ):
        "show prints normalized JSON"
        path = labconfig.templatePath( labconfig.languageByKey( 'json' ) )
        code, out, _ = self.mnconfig( 'show', path )
        self.assertEqual( code, 0 )
        self.assertEqual( json.loads( out )[ 'network' ][ 'datapath' ],
                          'auto' )
        code, out, _ = self.mnconfig( 'validate', path )
        self.assertEqual( code, 0 )
        self.assertIn( '3 hosts', out )

    def testSchemaAndLanguages( self ):
        "Reference output"
        code, out, _ = self.mnconfig( 'schema' )
        self.assertEqual( code, 0 )
        for heading in ( 'EDIT FREELY', 'ADVANCED', 'DO NOT EDIT' ):
            self.assertIn( heading, out )
        code, out, _ = self.mnconfig( 'languages' )
        self.assertEqual( code, 0 )
        self.assertIn( 'COBOL', out )

    def testRunNeedsRoot( self ):
        "run refuses to start without root"
        if os.geteuid() == 0:
            self.skipTest( 'running as root' )
        path = labconfig.templatePath( labconfig.languageByKey( 'json' ) )
        code, _, err = self.mnconfig( 'run', path )
        self.assertEqual( code, 1 )
        self.assertIn( 'sudo', err )


if __name__ == '__main__':
    sys.exit( unittest.main() )
