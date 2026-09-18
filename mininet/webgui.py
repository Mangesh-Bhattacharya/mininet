"""
mn-gui: a browser-based GUI for Mininet lab configurations.

  sudo mn-gui --config lab.yaml        then open the printed URL

Draw the topology, edit and validate the configuration, start and stop
the network, run pingall/iperf and run commands on hosts - from any
browser, including one on the Windows or macOS machine that runs the
Mininet container or VM.

Security model (see SECURITY.md):

- Listens on 127.0.0.1 only, unless --host (or MININET_GUI_HOST, set in
  the Docker image) says otherwise. Publish container ports to
  127.0.0.1 only: docker run -p 127.0.0.1:8080:8080 ...
- Every API call needs a random access token, printed at startup (or
  set with MININET_GUI_TOKEN). The token travels in the URL fragment,
  which browsers never send to servers or put in Referer headers.
- Requests whose Host header isn't this server (DNS rebinding) are
  refused, the API needs a custom header (so other web sites can't
  post forms to it), and pages are served with a strict
  Content-Security-Policy.
- Anyone with the token can run commands as root on emulated hosts,
  just like the Mininet CLI. Treat it like a root password.

Uses only the Python standard library.
"""

import argparse
import hmac
import io
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from mininet import labconfig
from mininet.labconfig import ConfigError

STATIC_DIR = os.path.join( os.path.dirname( os.path.abspath( __file__ ) ),
                           'webgui_static' )
STATIC_FILES = { '/': ( 'index.html', 'text/html; charset=utf-8' ),
                 '/app.js': ( 'app.js', 'text/javascript; charset=utf-8' ),
                 '/style.css': ( 'style.css', 'text/css; charset=utf-8' ) }

MAX_BODY = 1024 * 1024
MAX_OUTPUT = 64 * 1024
EXEC_TIMEOUT = 30
PING_HOST_LIMIT = 32

SECURITY_HEADERS = {
    'Content-Security-Policy':
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'",
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Cache-Control': 'no-store',
}

DEFAULT_CONFIG = os.path.join( labconfig.TEMPLATE_DIR, 'lab.yaml' )


class GuiError( Exception ):
    "An API request that can't be completed; status is the HTTP status"

    def __init__( self, message, status=400 ):
        Exception.__init__( self, message )
        self.status = status


def isRoot():
    "Are we running as root (needed to start networks)?"
    return hasattr( os, 'geteuid' ) and os.geteuid() == 0


def writeFile( path, text ):
    """Atomically replace path with text, keeping its owner and mode, so
       a file saved by sudo mn-gui stays editable by its owner. New files
       belong to labconfig.fileOwner() (the user who ran sudo)."""
    directory = os.path.dirname( os.path.abspath( path ) )
    fd, tmp = tempfile.mkstemp( dir=directory, prefix='.mn-gui-' )
    try:
        with io.open( fd, 'w', encoding='utf-8' ) as f:
            f.write( text )
        if os.path.exists( path ):
            st = os.stat( path )
            mode, owner = st.st_mode & 0o777, ( st.st_uid, st.st_gid )
        else:
            mode, owner = 0o644, labconfig.fileOwner()
        os.chmod( tmp, mode )
        if owner and isRoot():
            try:
                os.chown( tmp, owner[ 0 ], owner[ 1 ] )
            except OSError:
                pass  # e.g. file systems without Unix ownership
        os.replace( tmp, path )
    except OSError:
        os.unlink( tmp )
        raise


class LabSession( object ):
    """The configuration being edited and the network (if any) built
       from it. Mininet is not thread-safe, so every method that touches
       the network holds self.lock."""

    def __init__( self, path=None, netFactory=None ):
        self.path = path or DEFAULT_CONFIG
        self.readOnly = path is None
        self.lang = labconfig.languageFor( self.path )
        self.text = ''
        self.cfg = None
        self.issues = []
        self.net = None
        self.lock = threading.RLock()
        self.netFactory = netFactory or labconfig.buildNet
        self.reload()

    # Configuration

    def editable( self ):
        "Can the GUI edit and save this configuration?"
        return self.lang.isData() and not self.readOnly

    def reload( self ):
        "(Re)read the configuration file"
        with self.lock:
            self.text = labconfig.readText( self.path )
            try:
                self.cfg = labconfig.load( self.path )
                self.issues = []
            except ConfigError as e:
                self.cfg, self.issues = None, e.issues

    def check( self, text ):
        "Validate text in this session's format; return ( cfg, issues )"
        if not self.lang.isData():
            raise GuiError( '%s configurations are edited in your editor; '
                            'use Reload after saving' % self.lang.title )
        try:
            data = labconfig.parseText( text, self.lang.key, 'config' )
            return labconfig.validate( data ), []
        except ConfigError as e:
            return None, e.issues

    def save( self, text ):
        "Validate text and, if valid, write it to the configuration file"
        if not self.editable():
            raise GuiError( 'this configuration is read-only: start mn-gui '
                            'with --config FILE to edit your own file', 403 )
        cfg, issues = self.check( text )
        if issues:
            return issues
        with self.lock:
            writeFile( self.path, text )
            self.text, self.cfg, self.issues = text, cfg, []
        return []

    # Network

    def running( self ):
        "Is a network running?"
        return self.net is not None

    def requireNet( self ):
        "Return the running network or raise GuiError"
        if self.net is None:
            raise GuiError( 'the network is not running', 409 )
        return self.net

    def start( self ):
        "Build and start the network; return startup command output"
        with self.lock:
            if self.net is not None:
                raise GuiError( 'the network is already running', 409 )
            if self.cfg is None:
                raise GuiError( 'fix the configuration errors first', 409 )
            if not isRoot():
                raise GuiError( 'starting a network needs root: restart '
                                'with sudo mn-gui', 403 )
            net = self.netFactory( self.cfg )
            try:
                net.start()
                outputs = labconfig.runCommands( net, self.cfg )
            except Exception:
                net.stop()
                raise
            self.net = net
            return [ { 'command': c, 'output': o[ :MAX_OUTPUT ] }
                     for c, o in outputs ]

    def stop( self ):
        "Stop the network, if running"
        with self.lock:
            if self.net is not None:
                net, self.net = self.net, None
                net.stop()

    def node( self, name ):
        "Return a node of the running network"
        net = self.requireNet()
        if not isinstance( name, str ) or name not in net:
            raise GuiError( 'unknown node %r' % ( name, ), 404 )
        return net[ name ]

    def pingall( self ):
        "Ping between every pair of hosts; return a result matrix"
        with self.lock:
            net = self.requireNet()
            hosts = net.hosts[ :PING_HOST_LIMIT ]
            results, lost, sent = [], 0, 0
            for src in hosts:
                row = []
                for dst in hosts:
                    if src is dst:
                        row.append( None )
                        continue
                    out = src.cmd( 'ping -c1 -W1 %s' % dst.IP() )
                    tx, rx = net._parsePing( out )  # pylint: disable=W0212
                    sent += tx
                    lost += tx - rx
                    row.append( rx > 0 )
                results.append( { 'host': src.name, 'reached': row } )
            return { 'hosts': [ h.name for h in hosts ],
                     'rows': results,
                     'loss': round( 100.0 * lost / sent, 1 ) if sent else 0,
                     'truncated': len( net.hosts ) > PING_HOST_LIMIT }

    def iperf( self, src, dst ):
        "Measure TCP bandwidth from src to dst"
        with self.lock:
            net = self.requireNet()
            hosts = [ self.node( src ), self.node( dst ) ]
            if hosts[ 0 ] is hosts[ 1 ]:
                raise GuiError( 'choose two different hosts' )
            server, client = net.iperf( hosts, seconds=3 )
            return { 'server': server, 'client': client }

    def execute( self, name, command ):
        "Run a shell command on a node; return its output"
        if not isinstance( command, str ) or not command.strip():
            raise GuiError( 'enter a command' )
        if len( command ) > 4096:
            raise GuiError( 'command too long' )
        with self.lock:
            node = self.node( name )
            # A separate process in the node's namespaces, so a command
            # that never exits can't hang the node's shell
            proc = node.popen( [ 'bash', '-c', command ],
                               stdin=subprocess.DEVNULL,
                               stderr=subprocess.STDOUT )
        try:
            out, _ = proc.communicate( timeout=EXEC_TIMEOUT )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
            code = None
        text = out.decode( 'utf-8', 'replace' )
        return { 'output': text[ -MAX_OUTPUT: ], 'exitCode': code,
                 'timedOut': code is None }

    # Views

    def status( self ):
        "Summary for the GUI"
        cfg = self.cfg
        if self.net:
            hosts = [ h.name for h in self.net.hosts ]
        else:
            hosts = labconfig.buildTopo( cfg ).hosts() if cfg else []
        return {
            'running': self.running(), 'root': isRoot(),
            'path': self.path, 'language': self.lang.title,
            'format': self.lang.key, 'editable': self.editable(),
            'name': cfg[ 'name' ] if cfg else None,
            'description': cfg[ 'description' ] if cfg else '',
            'summary': labconfig.summary( cfg ) if cfg else '',
            'hosts': hosts,
            'nodes': sorted( self.net.nameToNode ) if self.net else [],
            'issues': [ i.asDict() for i in self.issues ] }


class GuiServer( ThreadingHTTPServer ):
    "HTTP server holding the session, token and allowed Host names"

    daemon_threads = True

    def __init__( self, address, session, token, allowedHosts=() ):
        self.session = session
        self.token = token
        self.allowedHosts = set( allowedHosts ) | {
            'localhost', '127.0.0.1', '[::1]' }
        ThreadingHTTPServer.__init__( self, address, Handler )


class Handler( BaseHTTPRequestHandler ):
    "Serves the static GUI and its JSON API"

    server_version = 'mn-gui'
    protocol_version = 'HTTP/1.1'

    def version_string( self ):
        "Server header without the Python version"
        return self.server_version

    def log_message( self, format, *args ):  # pylint: disable=W0622
        "Log requests at debug level only (URLs carry no secrets)"
        from mininet.log import debug  # pylint: disable=C0415
        debug( 'mn-gui: %s\n' % ( format % args ) )

    def end_headers( self ):
        for key, value in SECURITY_HEADERS.items():
            self.send_header( key, value )
        BaseHTTPRequestHandler.end_headers( self )

    def reply( self, status, body, contentType ):
        "Send a complete response"
        self.send_response( status )
        self.send_header( 'Content-Type', contentType )
        self.send_header( 'Content-Length', str( len( body ) ) )
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write( body )

    def replyJson( self, status, data ):
        "Send a JSON response"
        self.reply( status, json.dumps( data ).encode( 'utf-8' ),
                    'application/json' )

    def hostAllowed( self ):
        "Refuse requests for other host names (DNS rebinding)"
        host = ( self.headers.get( 'Host' ) or '' ).lower()
        name = host.rsplit( ':', 1 )[ 0 ] if not host.endswith( ']' ) \
            else host
        if name in self.server.allowedHosts:
            return True
        self.replyJson( 421, { 'error': 'unexpected Host header; start '
                                        'mn-gui with --allow-host %s' %
                                        name } )
        return False

    def authorized( self ):
        "Check the access token"
        header = self.headers.get( 'Authorization' ) or ''
        token = header[ 7: ] if header.startswith( 'Bearer ' ) else ''
        if token and hmac.compare_digest( token.encode(),
                                          self.server.token.encode() ):
            return True
        self.replyJson( 401, { 'error': 'missing or wrong access token' } )
        return False

    def do_GET( self ):  # pylint: disable=invalid-name
        "Static files and read-only API calls"
        if not self.hostAllowed():
            return
        path = urlsplit( self.path ).path
        if path in STATIC_FILES:
            name, contentType = STATIC_FILES[ path ]
            with io.open( os.path.join( STATIC_DIR, name ), 'rb' ) as f:
                self.reply( 200, f.read(), contentType )
        elif path.startswith( '/api/' ):
            if self.authorized():
                self.api( 'GET', path[ 5: ], None )
        else:
            self.replyJson( 404, { 'error': 'not found' } )

    do_HEAD = do_GET

    def do_POST( self ):  # pylint: disable=invalid-name
        "API calls that change state"
        if not self.hostAllowed() or not self.authorized():
            return
        if 'application/json' not in ( self.headers.get( 'Content-Type' )
                                       or '' ):
            self.replyJson( 415, { 'error': 'send application/json' } )
            return
        try:
            length = int( self.headers.get( 'Content-Length' ) or 0 )
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self.replyJson( 413, { 'error': 'request too large' } )
            self.close_connection = True  # pylint: disable=W0201
            return
        try:
            body = json.loads( self.rfile.read( length ) or b'{}' )
        except ValueError:
            self.replyJson( 400, { 'error': 'invalid JSON' } )
            return
        if not isinstance( body, dict ):
            self.replyJson( 400, { 'error': 'send a JSON object' } )
            return
        self.api( 'POST', urlsplit( self.path ).path[ 5: ], body )

    def api( self, method, name, body ):
        "Dispatch an API call"
        route = ROUTES.get( ( method, name ) )
        if route is None:
            self.replyJson( 404, { 'error': 'no such API call' } )
            return
        try:
            self.replyJson( 200, route( self.server.session, body or {} ) )
        except GuiError as e:
            self.replyJson( e.status, { 'error': str( e ) } )
        except ConfigError as e:
            self.replyJson( 400, { 'error': 'configuration problem',
                                   'issues': [ i.asDict()
                                               for i in e.issues ] } )
        except Exception as e:  # pylint: disable=broad-except
            from mininet.log import error  # pylint: disable=C0415
            error( 'mn-gui: %s failed: %r\n' % ( name, e ) )
            self.replyJson( 500, { 'error': '%s failed: %s' % ( name, e ) } )


def _validate( session, body ):
    "POST /api/validate"
    cfg, issues = session.check( body.get( 'text', '' ) )
    return { 'ok': not issues, 'issues': [ i.asDict() for i in issues ],
             'graph': labconfig.graph( cfg ) if cfg else None,
             'summary': labconfig.summary( cfg ) if cfg else '' }


def _save( session, body ):
    "POST /api/save"
    issues = session.save( body.get( 'text', '' ) )
    return { 'ok': not issues, 'issues': [ i.asDict() for i in issues ] }


def _graph( session, _body ):
    "GET /api/graph"
    return labconfig.graph( session.cfg ) if session.cfg else {
        'nodes': [], 'links': [] }


def _reload( session, _body ):
    "POST /api/reload"
    if session.running():
        raise GuiError( 'stop the network before reloading', 409 )
    session.reload()
    return session.status()


ROUTES = {
    ( 'GET', 'status' ): lambda s, b: s.status(),
    ( 'GET', 'config' ): lambda s, b: { 'text': s.text,
                                        'format': s.lang.key,
                                        'editable': s.editable() },
    ( 'GET', 'graph' ): _graph,
    ( 'GET', 'schema' ): lambda s, b: { 'fields': [
        { 'path': p, 'level': l, 'text': t }
        for p, l, t in labconfig.FIELDS ] },
    ( 'POST', 'validate' ): _validate,
    ( 'POST', 'save' ): _save,
    ( 'POST', 'reload' ): _reload,
    ( 'POST', 'start' ): lambda s, b: { 'startup': s.start() },
    ( 'POST', 'stop' ): lambda s, b: s.stop() or { 'ok': True },
    ( 'POST', 'pingall' ): lambda s, b: s.pingall(),
    ( 'POST', 'iperf' ): lambda s, b: s.iperf( b.get( 'src' ),
                                               b.get( 'dst' ) ),
    ( 'POST', 'exec' ): lambda s, b: s.execute( b.get( 'node' ),
                                                b.get( 'command' ) ),
}


def parser():
    "Argument parser for mn-gui"
    p = argparse.ArgumentParser(
        prog='mn-gui', description='Browser GUI for Mininet labs. '
        'Run with sudo to start networks.' )
    p.add_argument( '--config', '-c',
                    help='lab configuration to edit and run (any '
                    'language mn-config supports; default: a read-only '
                    'example)' )
    p.add_argument( '--host', default=os.environ.get( 'MININET_GUI_HOST',
                                                      '127.0.0.1' ),
                    help='address to listen on (default 127.0.0.1; only '
                    'change it inside a container or on a trusted '
                    'network)' )
    p.add_argument( '--port', '-p', type=int,
                    help='port (default: gui.port from the config, 8080)' )
    p.add_argument( '--allow-host', action='append', default=[],
                    metavar='NAME', help='extra host name the browser '
                    'may use to reach the GUI (repeatable)' )
    p.add_argument( '--verbosity', '-v', default='info',
                    help='log level: info, debug...' )
    return p


def main( argv=None ):
    "Entry point for mn-gui"
    args = parser().parse_args( argv )
    from mininet.log import setLogLevel, info, warn  # pylint: disable=C0415
    setLogLevel( args.verbosity )
    try:
        if args.config and not os.path.exists( args.config ):
            # Start a new lab from the matching starter template
            lang = labconfig.languageFor( args.config )
            if not lang.isData():
                raise ConfigError( labconfig.Issue(
                    args.config, 'file not found',
                    'create it with: mn-config init --lang %s -o %s' %
                    ( lang.key, args.config ) ) )
            with io.open( labconfig.templatePath( lang ),
                          encoding='utf-8' ) as f:
                writeFile( args.config, f.read() )
            info( '*** Created %s from the %s template\n' %
                  ( args.config, lang.title ) )
        session = LabSession( args.config )
    except ConfigError as e:
        print( 'mn-gui: %s' % e, file=sys.stderr )
        return 2
    port = args.port if args.port is not None else (
        session.cfg or {} ).get( 'gui', {} ).get( 'port', 8080 )
    token = os.environ.get( 'MININET_GUI_TOKEN' ) or secrets.token_urlsafe(
        24 )
    if len( token ) < 16:
        print( 'mn-gui: MININET_GUI_TOKEN must be at least 16 characters',
               file=sys.stderr )
        return 2
    server = GuiServer( ( args.host, port ), session, token,
                        args.allow_host )
    if args.host not in ( '127.0.0.1', 'localhost', '::1' ):
        warn( '*** mn-gui is listening on %s: anyone who can reach this '
              'port and knows the token can run commands as root.\n'
              '*** In Docker, publish it to 127.0.0.1 only '
              '(-p 127.0.0.1:%d:%d).\n' % ( args.host, port, port ) )
    if not isRoot():
        warn( '*** Not running as root: you can edit and validate '
              'configurations, but not start networks (use sudo).\n' )
    info( '*** Mininet GUI for %s\n' % session.path )
    info( '*** Open this URL in your browser (it contains your access '
          'token):\n\n    http://localhost:%d/#token=%s\n\n' %
          ( port, token ) )
    info( '*** Press Ctrl-C to stop\n' )

    def shutdown( *_args ):
        "Stop the network and exit on SIGTERM"
        raise KeyboardInterrupt
    previous = signal.signal( signal.SIGTERM, shutdown )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        info( '\n*** Stopping\n' )
        signal.signal( signal.SIGTERM, previous )
        server.server_close()
        session.stop()
    return 0


if __name__ == '__main__':
    sys.exit( main() )
