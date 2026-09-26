#!/usr/bin/env python3
"""
End-to-end test of the mn-gui browser GUI in a real browser (Chromium,
driven by Playwright), which also captures the screenshots used in the
documentation.

  gui-browser-test.py URL TOKEN OUTDIR [--no-network]

URL is the mn-gui base URL (http://localhost:8765), TOKEN its access
token and OUTDIR where screenshots go. --no-network skips starting a
network (for mn-gui running without root).

The test fails on any browser console error, so a Content-Security-
Policy violation or a JavaScript exception fails it.
"""

import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

TIMEOUT = 120 * 1000   # ms; starting a network can take a while


def shot( page, outdir, name ):
    "Save a screenshot of the whole page"
    path = os.path.join( outdir, name )
    page.screenshot( path=path, full_page=True )
    print( 'saved', path )


def check_config_and_validation( page, outdir, suffix ):
    "Topology drawn, config loaded, live validation reports mistakes"
    expect( page.locator( '#status-pill' ) ).to_have_text(
        re.compile( 'Stopped|Running' ), timeout=TIMEOUT )
    # 3 hosts in the starter lab, 4 once the editor pass has added one
    expect( page.locator( '#graph rect.switch' ) ).to_have_count( 2 )
    page.wait_for_function(
        "() => document.querySelectorAll"
        "( '#graph circle.host' ).length >= 3" )
    expect( page.locator( '#editor' ) ).to_have_value(
        re.compile( 'two-switch-lab' ) )
    shot( page, outdir, 'gui-overview%s.png' % suffix )

    original = page.locator( '#editor' ).input_value()
    # A name with a space, which also breaks the links that use it
    broken = original.replace( 'name: h1', 'name: h 1', 1 )
    assert broken != original, 'could not find a host to break'
    page.locator( '#editor' ).fill( broken )
    page.wait_for_function(
        "() => document.querySelectorAll( '#issues li' ).length >= 2" )
    expect( page.locator( '#issues' ) ).to_contain_text( 'Hint:' )
    expect( page.locator( '#issues' ) ).to_contain_text( 'invalid name' )
    expect( page.locator( '#btn-save' ) ).to_be_disabled()
    page.locator( '#issues' ).scroll_into_view_if_needed()
    shot( page, outdir, 'gui-validation%s.png' % suffix )

    page.locator( '#editor' ).fill( original )
    expect( page.locator( '#valid-state' ) ).to_have_text( 'Valid' )
    expect( page.locator( '#issues li' ) ).to_have_count( 0 )

    page.locator( '#tab-guide' ).click()
    expect( page.locator( '#guide' ) ).to_contain_text( 'Do not edit' )
    shot( page, outdir, 'gui-guide%s.png' % suffix )
    page.locator( '#tab-config' ).click()


def check_editor( page, outdir, suffix ):
    """Build a topology with the editor: add a host, link it, give it an
       address, move it, delete something, then save the file"""
    canvas = page.locator( '#graph' )
    box = canvas.bounding_box()

    # Add a host with the host tool
    page.locator( 'button[data-tool=host]' ).click()
    canvas.click( position={ 'x': 70, 'y': box[ 'height' ] - 80 } )
    expect( page.locator( '#graph g[data-node=h4]' ) ).to_have_count( 1 )
    expect( page.locator( '#editor' ) ).to_have_value(
        re.compile( 'h4' ) )

    # Link it to a switch
    page.locator( 'button[data-tool=link]' ).click()
    page.locator( '#graph g[data-node=h4]' ).click()
    page.locator( '#graph g[data-node=s2]' ).click()
    expect( page.locator( '#props' ) ).to_contain_text( 'Link' )

    # Give the host an address through the properties form
    page.locator( 'button[data-tool=select]' ).click()
    page.locator( '#graph g[data-node=h4]' ).click()
    expect( page.locator( '#props' ) ).to_contain_text( 'Host h4' )
    page.locator( '#prop-ip' ).fill( '10.0.0.4/24' )
    page.locator( '#props button[type=submit]' ).click()
    expect( page.locator( '#editor' ) ).to_have_value(
        re.compile( r'10\.0\.0\.4/24' ) )
    shot( page, outdir, 'gui-editor%s.png' % suffix )

    # Move it: the position is written to the file
    node = page.locator( '#graph g[data-node=h4]' )
    start = node.bounding_box()
    page.mouse.move( start[ 'x' ] + start[ 'width' ] / 2,
                     start[ 'y' ] + start[ 'height' ] / 2 )
    page.mouse.down()
    page.mouse.move( start[ 'x' ] + 40, start[ 'y' ] - 30, steps=8 )
    page.mouse.up()
    expect( page.locator( '#editor' ) ).to_have_value( re.compile( 'x: ' ) )

    # Delete the spare host we do not want, with the delete tool
    page.locator( 'button[data-tool=host]' ).click()
    canvas.click( position={ 'x': box[ 'width' ] - 70, 'y': 70 } )
    expect( page.locator( '#graph g[data-node=h5]' ) ).to_have_count( 1 )
    page.locator( 'button[data-tool=delete]' ).click()
    page.locator( '#graph g[data-node=h5]' ).click()
    expect( page.locator( '#graph g[data-node=h5]' ) ).to_have_count( 0 )
    page.locator( 'button[data-tool=select]' ).click()

    # Tidy up and save
    page.locator( '#btn-arrange' ).click()
    expect( page.locator( '#btn-save' ) ).to_be_enabled()
    page.locator( '#btn-save' ).click()
    expect( page.locator( '#notice' ) ).to_contain_text( 'Saved' )
    expect( page.locator( '#btn-save' ) ).to_be_disabled()
    expect( page.locator( '#issues li' ) ).to_have_count( 0 )


def wait_for( page, condition ):
    "Wait until condition (JS) holds; fail at once if the GUI shows an error"
    page.wait_for_function(
        "() => (%s) || document.getElementById( 'notice' )"
        ".classList.contains( 'error' )" % condition, timeout=TIMEOUT )
    notice = page.locator( '#notice' )
    if 'error' in ( notice.get_attribute( 'class' ) or '' ):
        raise SystemExit( 'GUI error: %s' % notice.inner_text() )


def check_network( page, outdir, suffix ):
    "Start, ping all, run commands, iperf, stop"
    page.locator( '#btn-start' ).click()
    wait_for( page, "document.getElementById( 'status-pill' ).textContent"
                    " === 'Running'" )
    # Every host lights up; the editor pass may have added one
    page.wait_for_function(
        "() => document.querySelectorAll"
        "( '#graph circle.halo[visibility=visible]' ).length >= 3" )

    page.locator( '#btn-pingall' ).click()
    expect( page.locator( '#ping-result' ) ).to_contain_text(
        'All hosts can reach each other', timeout=TIMEOUT )
    expect( page.locator( '#ping-result td.no' ) ).to_have_count( 0 )
    expect( page.locator( '#ping-result' ) ).not_to_contain_text( 'null' )
    expect( page.locator( '#btn-pingall' ) ).to_be_enabled()
    shot( page, outdir, 'gui-pingall%s.png' % suffix )

    page.locator( '#tab-console' ).click()
    page.locator( '#exec-node' ).select_option( 'h1' )
    page.locator( '#exec-cmd' ).fill( 'ping -c 2 10.0.0.3' )
    page.locator( '#exec-form button[type=submit]' ).click()
    expect( page.locator( '#console' ) ).to_contain_text(
        '2 received', timeout=TIMEOUT )
    page.locator( '#iperf-src' ).select_option( 'h1' )
    page.locator( '#iperf-dst' ).select_option( 'h3' )
    page.locator( '#iperf-form button[type=submit]' ).click()
    expect( page.locator( '#console' ) ).to_contain_text(
        'bits/sec', timeout=TIMEOUT )
    expect( page.locator( '#btn-pingall' ) ).to_be_enabled()
    shot( page, outdir, 'gui-console%s.png' % suffix )

    page.locator( '#btn-stop' ).click()
    expect( page.locator( '#status-pill' ) ).to_have_text(
        'Stopped', timeout=TIMEOUT )


def run( browser, url, token, outdir, scheme, network, edit ):
    "One pass through the GUI in a colour scheme"
    suffix = '' if scheme == 'light' else '-dark'
    context = browser.new_context( viewport={ 'width': 1440, 'height': 900 },
                                   color_scheme=scheme,
                                   device_scale_factor=1 )
    page = context.new_page()
    page.set_default_timeout( 30 * 1000 )
    errors = []
    page.on( 'console', lambda msg: msg.type == 'error' and errors.append(
        msg.text ) )
    page.on( 'pageerror', lambda exc: errors.append( str( exc ) ) )

    # A wrong token is refused and asks for the right one
    page.goto( '%s/#token=wrong-token-0000000000' % url )
    expect( page.locator( '#token-dialog' ) ).to_be_visible()
    errors[:] = [ e for e in errors if '401' not in e ]
    # The token leaves the address bar once read
    page.goto( '%s/#token=%s' % ( url, token ) )
    expect( page.locator( '#status-pill' ) ).not_to_have_text( '...' )
    assert token not in page.url, 'token left in the URL'

    check_config_and_validation( page, outdir, suffix )
    if edit:
        check_editor( page, outdir, suffix )
    if network:
        check_network( page, outdir, suffix )
    context.close()
    if errors:
        raise SystemExit( 'browser console errors:\n  ' +
                          '\n  '.join( errors ) )


def main():
    "Run the test in light and dark mode"
    args = [ a for a in sys.argv[ 1: ] if not a.startswith( '--' ) ]
    if len( args ) != 3:
        raise SystemExit( __doc__ )
    url, token, outdir = args
    network = '--no-network' not in sys.argv
    os.makedirs( outdir, exist_ok=True )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for scheme in ( 'light', 'dark' ):
                # The editor pass changes the file, so run it once
                run( browser, url.rstrip( '/' ), token, outdir, scheme,
                     network, edit=scheme == 'light' )
        finally:
            browser.close()
    print( 'mn-gui browser test passed' )


if __name__ == '__main__':
    main()
