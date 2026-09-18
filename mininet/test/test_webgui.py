#!/usr/bin/env python3

"""
Unit tests for mininet.webgui (the mn-gui browser GUI), including its
security checks. A fake network stands in for Mininet, so these don't
need root or Open vSwitch:

  python3 -m unittest mininet.test.test_webgui -v
"""

import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from mininet import labconfig, webgui

TOKEN = 'test-token-0123456789abcdef'


class FakeNode( object ):
    "Just enough of a Mininet host"

    def __init__( self, name, ip ):
        self.name = name
        self.ip = ip

    def IP( self ):  # pylint: disable=invalid-name
        "Address"
        return self.ip

    @staticmethod
    def cmd( command ):
        "Pretend every ping works"
        if command.startswith( 'ping' ):
            return '1 packets transmitted, 1 received, 0% packet loss'
        return 'ran %s\n' % command

    @staticmethod
    def popen( args, **kwargs ):
        "Run locally instead of in a namespace"
        kwargs.setdefault( 'stdout', subprocess.PIPE )
        return subprocess.Popen( args, **kwargs )


class FakeNet( object ):
    "Just enough of a Mininet network"

    def __init__( self, cfg ):
        topo = labconfig.buildTopo( cfg )
        self.hosts = [ FakeNode( h, '10.0.0.%d' % ( i + 1 ) )
                       for i, h in enumerate( topo.hosts() ) ]
        self.nameToNode = { h.name: h for h in self.hosts }
        self.started = self.stopped = False

    def start( self ):
        "Start"
        self.started = True

    def stop( self ):
        "Stop"
        self.stopped = True

    def __contains__( self, name ):
        return name in self.nameToNode

    def __getitem__( self, name ):
        return self.nameToNode[ name ]

    @staticmethod
    def _parsePing( output ):  # pylint: disable=invalid-name
        "Same contract as Mininet._parsePing"
        return ( 1, 1 ) if '1 received' in output else ( 1, 0 )

    @staticmethod
    def iperf( hosts, seconds=5 ):
        "Pretend bandwidth"
        assert len( hosts ) == 2 and seconds
        return [ '9.5 Mbits/sec', '9.8 Mbits/sec' ]


class GuiTestCase( unittest.TestCase ):
    "Starts mn-gui on a free port for each test"

    config = None
    root = True

    def setUp( self ):
        self.tmp = tempfile.mkdtemp()
        path = None
        if self.config is not None:
            path = os.path.join( self.tmp, 'lab.yaml' )
            with io.open( path, 'w' ) as f:
                f.write( self.config )
        self.path = path
        self.session = webgui.LabSession( path, netFactory=FakeNet )
        patcher = mock.patch.object( webgui, 'isRoot',
                                     return_value=self.root )
        patcher.start()
        self.addCleanup( patcher.stop )
        self.server = webgui.GuiServer( ( '127.0.0.1', 0 ), self.session,
                                        TOKEN )
        self.port = self.server.server_address[ 1 ]
        thread = threading.Thread( target=self.server.serve_forever )
        thread.daemon = True
        thread.start()

    def tearDown( self ):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree( self.tmp )

    def request( self, method, path, body=None,  # pylint: disable=R0913
                 token=TOKEN, host='localhost', headers=None ):
        "Make a request; return ( status, headers, parsed body )"
        conn = http.client.HTTPConnection( '127.0.0.1', self.port,
                                           timeout=10 )
        hdrs = { 'Host': host }
        if token:
            hdrs[ 'Authorization' ] = 'Bearer ' + token
        data = None
        if body is not None:
            data = body if isinstance( body, bytes ) else json.dumps(
                body ).encode()
            hdrs[ 'Content-Type' ] = 'application/json'
        hdrs.update( headers or {} )
        conn.request( method, path, body=data, headers=hdrs )
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            parsed = json.loads( raw )
        except ValueError:
            parsed = raw
        return resp.status, resp.headers, parsed

    def api( self, method, name, body=None ):
        "Successful API call"
        status, _, data = self.request( method, '/api/' + name, body )
        self.assertEqual( status, 200, data )
        return data


VALID = labconfig.readText( os.path.join( labconfig.TEMPLATE_DIR,
                                          'lab.yaml' ) )


class SecurityTests( GuiTestCase ):
    "Authentication, Host checks, headers, limits"

    config = VALID

    def testStaticFilesAndHeaders( self ):
        "The page loads without a token, with a strict CSP"
        status, headers, body = self.request( 'GET', '/', token=None )
        self.assertEqual( status, 200 )
        self.assertIn( b'Mininet Lab', body )
        csp = headers[ 'Content-Security-Policy' ]
        self.assertIn( "script-src 'self'", csp )
        self.assertIn( "frame-ancestors 'none'", csp )
        self.assertEqual( headers[ 'X-Content-Type-Options' ], 'nosniff' )
        self.assertEqual( headers[ 'Referrer-Policy' ], 'no-referrer' )
        self.assertEqual( headers[ 'Server' ], 'mn-gui' )

    def testOnlyKnownFiles( self ):
        "No directory listing or path traversal"
        for path in ( '/../webgui.py', '/%2e%2e/webgui.py', '/app.js/..',
                      '/etc/passwd', '/webgui_static/app.js' ):
            status, _, _ = self.request( 'GET', path, token=None )
            self.assertEqual( status, 404, path )

    def testTokenRequired( self ):
        "API calls need the right token"
        for token in ( None, 'wrong-token-0123456789', TOKEN + 'x' ):
            status, _, data = self.request( 'GET', '/api/status',
                                            token=token )
            self.assertEqual( status, 401 )
            self.assertIn( 'token', data[ 'error' ] )
        self.api( 'GET', 'status' )

    def testTokenInQueryStringIgnored( self ):
        "Tokens only count in the Authorization header"
        status, _, _ = self.request( 'GET', '/api/status?token=' + TOKEN,
                                     token=None )
        self.assertEqual( status, 401 )

    def testDnsRebindingBlocked( self ):
        "Unknown Host headers are refused, even with the token"
        status, _, _ = self.request( 'GET', '/api/status',
                                     host='evil.example:8080' )
        self.assertEqual( status, 421 )
        for host in ( 'localhost:8080', '127.0.0.1', '[::1]:8080' ):
            status, _, _ = self.request( 'GET', '/api/status', host=host )
            self.assertEqual( status, 200, host )

    def testAllowHost( self ):
        "--allow-host adds names"
        self.server.allowedHosts.add( 'lab.local' )
        status, _, _ = self.request( 'GET', '/api/status',
                                     host='lab.local:8080' )
        self.assertEqual( status, 200 )

    def testPostNeedsJson( self ):
        "Form posts from other sites are rejected"
        status, _, _ = self.request(
            'POST', '/api/stop', body=b'a=b',
            headers={ 'Content-Type': 'application/x-www-form-urlencoded' } )
        self.assertEqual( status, 415 )

    def testBodyLimits( self ):
        "Oversized and malformed bodies"
        status, _, _ = self.request(
            'POST', '/api/validate', body=b'x',
            headers={ 'Content-Length': str( webgui.MAX_BODY + 1 ) } )
        self.assertEqual( status, 413 )
        status, _, _ = self.request( 'POST', '/api/validate', body=b'{bad' )
        self.assertEqual( status, 400 )
        status, _, _ = self.request( 'POST', '/api/validate', body=b'[1]' )
        self.assertEqual( status, 400 )

    def testUnknownApi( self ):
        "Unknown calls and methods"
        status, _, _ = self.request( 'GET', '/api/start' )
        self.assertEqual( status, 404 )
        status, _, _ = self.request( 'POST', '/api/nothing', body={} )
        self.assertEqual( status, 404 )


class ConfigTests( GuiTestCase ):
    "Editing configurations"

    config = VALID

    def testStatusAndConfig( self ):
        "Status reflects the file"
        status = self.api( 'GET', 'status' )
        self.assertEqual( status[ 'name' ], 'two-switch-lab' )
        self.assertTrue( status[ 'editable' ] )
        self.assertFalse( status[ 'running' ] )
        self.assertEqual( self.api( 'GET', 'config' )[ 'text' ], VALID )
        graph = self.api( 'GET', 'graph' )
        self.assertEqual( len( graph[ 'nodes' ] ), 6 )

    def testValidate( self ):
        "Validation returns issues or a graph"
        ok = self.api( 'POST', 'validate', { 'text': VALID } )
        self.assertTrue( ok[ 'ok' ] )
        self.assertTrue( ok[ 'graph' ][ 'nodes' ] )
        bad = self.api( 'POST', 'validate', { 'text': 'netwrok: {}' } )
        self.assertFalse( bad[ 'ok' ] )
        self.assertEqual( bad[ 'issues' ][ 0 ][ 'path' ], 'netwrok' )
        broken = self.api( 'POST', 'validate', { 'text': 'a: [' } )
        self.assertIn( 'invalid YAML', broken[ 'issues' ][ 0 ][ 'message' ] )

    def testYamlCannotCreateObjects( self ):
        "safe_load: no Python objects from YAML"
        result = self.api( 'POST', 'validate', {
            'text': 'name: !!python/object/apply:os.system ["true"]' } )
        self.assertFalse( result[ 'ok' ] )

    def testSave( self ):
        "Valid text is saved; invalid text is not"
        text = VALID.replace( 'two-switch-lab', 'renamed-lab' )
        self.assertTrue( self.api( 'POST', 'save', { 'text': text } )[ 'ok' ] )
        self.assertEqual( labconfig.readText( self.path ), text )
        self.assertEqual( self.api( 'GET', 'status' )[ 'name' ],
                          'renamed-lab' )
        result = self.api( 'POST', 'save', { 'text': 'version: 7' } )
        self.assertFalse( result[ 'ok' ] )
        self.assertEqual( labconfig.readText( self.path ), text )
        self.assertEqual( [ f for f in os.listdir( self.tmp )
                            if f.startswith( '.mn-gui' ) ], [] )


class ReadOnlyTests( GuiTestCase ):
    "Without --config the example is read-only"

    def testReadOnly( self ):
        "Save is refused"
        self.assertFalse( self.api( 'GET', 'status' )[ 'editable' ] )
        status, _, _ = self.request( 'POST', '/api/save',
                                     { 'text': VALID } )
        self.assertEqual( status, 403 )


class NotRootTests( GuiTestCase ):
    "Without root, networks can't start"

    config = VALID
    root = False

    def testStartNeedsRoot( self ):
        "403 with a hint"
        status, _, data = self.request( 'POST', '/api/start', {} )
        self.assertEqual( status, 403 )
        self.assertIn( 'sudo', data[ 'error' ] )


class InvalidConfigTests( GuiTestCase ):
    "A broken file loads, but can't be started"

    config = 'hosts: [ { name: "bad name" } ]\n'

    def testCannotStart( self ):
        "Issues are reported and start is refused"
        status = self.api( 'GET', 'status' )
        self.assertIsNone( status[ 'name' ] )
        self.assertTrue( status[ 'issues' ] )
        code, _, _ = self.request( 'POST', '/api/start', {} )
        self.assertEqual( code, 409 )


class NetworkTests( GuiTestCase ):
    "Start, test, run commands, stop"

    config = VALID

    def testLifecycle( self ):
        "Full session against the fake network"
        startup = self.api( 'POST', 'start', {} )[ 'startup' ]
        self.assertEqual( startup[ 0 ][ 'command' ], 'h1 ip -brief address' )
        status = self.api( 'GET', 'status' )
        self.assertTrue( status[ 'running' ] )
        self.assertEqual( status[ 'nodes' ], [ 'h1', 'h2', 'h3' ] )
        code, _, _ = self.request( 'POST', '/api/start', {} )
        self.assertEqual( code, 409 )
        code, _, _ = self.request( 'POST', '/api/reload', {} )
        self.assertEqual( code, 409 )

        ping = self.api( 'POST', 'pingall', {} )
        self.assertEqual( ping[ 'loss' ], 0 )
        self.assertEqual( ping[ 'rows' ][ 0 ][ 'reached' ],
                          [ None, True, True ] )

        result = self.api( 'POST', 'exec', { 'node': 'h1',
                                             'command': 'echo hello' } )
        self.assertEqual( result[ 'output' ], 'hello\n' )
        self.assertEqual( result[ 'exitCode' ], 0 )
        for body, code in ( ( { 'node': 'h9', 'command': 'id' }, 404 ),
                            ( { 'node': [ 'h1' ], 'command': 'id' }, 404 ),
                            ( { 'node': 'h1', 'command': ' ' }, 400 ),
                            ( { 'node': 'h1', 'command': 'x' * 5000 },
                              400 ) ):
            status, _, _ = self.request( 'POST', '/api/exec', body )
            self.assertEqual( status, code, body )

        bw = self.api( 'POST', 'iperf', { 'src': 'h1', 'dst': 'h3' } )
        self.assertIn( 'Mbits', bw[ 'server' ] )
        status, _, _ = self.request( 'POST', '/api/iperf',
                                     { 'src': 'h1', 'dst': 'h1' } )
        self.assertEqual( status, 400 )

        net = self.session.net
        self.api( 'POST', 'stop', {} )
        self.assertTrue( net.stopped )
        self.assertFalse( self.api( 'GET', 'status' )[ 'running' ] )
        status, _, _ = self.request( 'POST', '/api/pingall', {} )
        self.assertEqual( status, 409 )

    def testCommandTimeout( self ):
        "Commands that never finish are stopped"
        self.api( 'POST', 'start', {} )
        with mock.patch.object( webgui, 'EXEC_TIMEOUT', 0.5 ):
            result = self.api( 'POST', 'exec', { 'node': 'h1',
                                                 'command': 'sleep 30' } )
        self.assertTrue( result[ 'timedOut' ] )
        self.api( 'POST', 'stop', {} )


class MainTests( unittest.TestCase ):
    "mn-gui command line"

    def testShortTokenRejected( self ):
        "MININET_GUI_TOKEN must be long enough"
        with mock.patch.dict( os.environ, { 'MININET_GUI_TOKEN': 'short' } ):
            with mock.patch( 'sys.stderr', io.StringIO() ):
                self.assertEqual( webgui.main( [ '--port', '0' ] ), 2 )

    def testDefaultHostIsLoopback( self ):
        "Listens on 127.0.0.1 unless told otherwise"
        with mock.patch.dict( os.environ, clear=False ) as env:
            env.pop( 'MININET_GUI_HOST', None )
            args = webgui.parser().parse_args( [] )
        self.assertEqual( args.host, '127.0.0.1' )

    def testCreatesMissingConfig( self ):
        "--config NEW.yaml starts from the template"
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join( tmp, 'new.yaml' )
            with mock.patch.object( webgui.GuiServer, 'serve_forever',
                                    side_effect=KeyboardInterrupt ):
                self.assertEqual( webgui.main(
                    [ '--config', path, '--port', '0',
                      '--verbosity', 'error' ] ), 0 )
            self.assertEqual( labconfig.load( path )[ 'name' ],
                              'two-switch-lab' )
        finally:
            shutil.rmtree( tmp )


if __name__ == '__main__':
    sys.exit( unittest.main() )
