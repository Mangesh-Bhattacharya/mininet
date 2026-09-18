#!/usr/bin/env python3

"""Package: mininet
   Unit tests for mininet.doctor (no root or network access needed)"""

import json
import sys
import unittest
from io import StringIO

from mininet.doctor import ( runChecks, report, detectEnvironment, suggest,
                             main, OK, WARN, FAIL, INFO )


class FakeEnv( object ):
    "Fake system: a set of files, commands and command results"

    # pylint: disable=too-many-arguments
    def __init__( self, system='Linux', files=None, contents=None,
                  commands=None, results=None, root=True ):
        self._system = system
        self.files = set( files or [] )
        self.contents = contents or {}
        self.commands = set( commands or [] )
        self.results = results or {}
        self.root = root

    def system( self ):
        "OS name"
        return self._system

    def exists( self, path ):
        "Fake file existence"
        return path in self.files or path in self.contents

    def read( self, path ):
        "Fake file contents"
        return self.contents.get( path, '' )

    def which( self, cmd ):
        "Fake PATH lookup"
        return '/usr/bin/%s' % cmd if cmd in self.commands else None

    def run( self, cmd ):
        "Fake command execution: unknown commands fail"
        return self.results.get( cmd, ( 1, '' ) )

    def isRoot( self ):
        "Fake euid check"
        return self.root

    @staticmethod
    def pythonVersion():
        "Fake Python version"
        return ( 3, 12 )


BASE_COMMANDS = [ 'mnexec', 'ip', 'ping', 'tc', 'brctl' ]
BASE_FILES = [ '/proc/self/ns/net', '/sys/module/bridge',
               '/sys/module/sch_htb', '/sys/module/sch_netem' ]


def fullEnv( **kwargs ):
    "A fully working native Linux machine with OVS and a controller"
    params = dict(
        files=BASE_FILES + [ '/sys/module/openvswitch' ],
        commands=BASE_COMMANDS + [ 'ovs-vsctl', 'ovs-testcontroller' ],
        results={ 'ovs-vsctl -t 2 show': ( 0, '' ) } )
    params.update( kwargs )
    return FakeEnv( **params )


def statuses( checks ):
    "Map check name -> status"
    return dict( ( c.name, c.status ) for c in checks )


class TestDoctor( unittest.TestCase ):
    "Test mininet doctor checks against fake environments"

    def testNonLinuxFails( self ):
        "Windows/macOS hosts get a single failure pointing at alternatives"
        where, checks, suggestion = runChecks( FakeEnv( system='Darwin' ) )
        self.assertEqual( where, 'darwin' )
        self.assertEqual( [ ( c.name, c.status ) for c in checks ],
                          [ ( 'linux', FAIL ) ] )
        self.assertIn( 'Docker', checks[ 0 ].hint )
        self.assertIsNone( suggestion )

    def testFullyWorking( self ):
        "Native Linux with OVS + controller suggests plain mn"
        where, checks, suggestion = runChecks( fullEnv() )
        self.assertEqual( where, 'native' )
        self.assertNotIn( FAIL, statuses( checks ).values() )
        self.assertEqual( statuses( checks )[ 'ovs-kernel' ], OK )
        self.assertEqual( suggestion, 'sudo mn --test pingall' )

    def testDockerDesktopUserspaceDatapath( self ):
        "Container without OVS kernel module still works (userspace)"
        env = fullEnv( files=BASE_FILES + [ '/.dockerenv' ] )
        where, checks, suggestion = runChecks( env )
        self.assertEqual( where, 'container' )
        self.assertEqual( statuses( checks )[ 'ovs-kernel' ], INFO )
        self.assertEqual( suggestion, 'sudo mn --test pingall' )

    def testNoController( self ):
        "OVS without a controller suggests ovsbr"
        env = fullEnv( commands=BASE_COMMANDS + [ 'ovs-vsctl' ] )
        _where, checks, suggestion = runChecks( env )
        self.assertEqual( statuses( checks )[ 'controller' ], WARN )
        self.assertIn( '--switch ovsbr', suggestion )

    def testOvsNotRunning( self ):
        "Installed but stopped OVS falls back to Linux bridge"
        env = fullEnv( results={} )
        _where, checks, suggestion = runChecks( env )
        self.assertEqual( statuses( checks )[ 'ovs' ], WARN )
        self.assertIn( '--switch lxbr', suggestion )

    def testMissingMnexecFails( self ):
        "Missing mnexec is fatal and reported with a hint"
        env = fullEnv( commands=[ 'ip', 'ping', 'tc', 'ovs-vsctl' ] )
        _where, checks, _suggestion = runChecks( env )
        self.assertEqual( statuses( checks )[ 'mnexec' ], FAIL )
        out = StringIO()
        self.assertEqual( report( 'native', checks, None, out ), 1 )
        self.assertIn( 'cannot run here', out.getvalue() )

    def testNotRoot( self ):
        "Non-root is a warning, not a failure"
        _where, checks, _suggestion = runChecks( fullEnv( root=False ) )
        self.assertEqual( statuses( checks )[ 'root' ], WARN )

    def testMissingQdiscs( self ):
        "Kernels without netem/htb warn about TCLink"
        env = fullEnv( files=[ '/proc/self/ns/net', '/sys/module/bridge',
                               '/sys/module/openvswitch' ] )
        _where, checks, _suggestion = runChecks( env )
        tc = [ c for c in checks if c.name == 'tc' ][ 0 ]
        self.assertEqual( tc.status, WARN )
        self.assertIn( 'sch_netem', tc.detail )

    def testDetectEnvironment( self ):
        "WSL, VMs and containers are recognized"
        wsl = FakeEnv( contents={ '/proc/version':
                                  'Linux 6.6.87-microsoft-standard-WSL2' } )
        self.assertEqual( detectEnvironment( wsl ), 'wsl' )
        vbox = FakeEnv( contents={ '/sys/class/dmi/id/product_name':
                                   'VirtualBox' } )
        self.assertEqual( detectEnvironment( vbox ), 'vm' )
        podman = FakeEnv( files=[ '/run/.containerenv' ] )
        self.assertEqual( detectEnvironment( podman ), 'container' )
        self.assertEqual( detectEnvironment( FakeEnv() ), 'native' )

    def testLinuxBridgeNeedsBrctl( self ):
        "--switch lxbr is only suggested when brctl is installed"
        env = fullEnv( commands=[ 'mnexec', 'ip', 'ping', 'tc',
                                  'ovs-vsctl' ], results={} )
        _where, checks, suggestion = runChecks( env )
        self.assertEqual( statuses( checks )[ 'bridge' ], WARN )
        self.assertIsNone( suggestion )

    def testSuggestNothingWorks( self ):
        "No switch available means no suggestion"
        self.assertIsNone( suggest( False, [], False ) )

    def testJsonOutput( self ):
        "--json produces parseable output on the real system"
        saved, sys.stdout = sys.stdout, StringIO()
        try:
            main( [ '--json' ] )
            data = json.loads( sys.stdout.getvalue() )
        finally:
            sys.stdout = saved
        self.assertIn( 'checks', data )
        self.assertIn( 'environment', data )


if __name__ == '__main__':
    unittest.main()
