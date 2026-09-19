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
    expect( page.locator( '#graph circle.host' ) ).to_have_count( 3 )
    expect( page.locator( '#graph rect.switch' ) ).to_have_count( 2 )
    expect( page.locator( '#editor' ) ).to_have_value(
        re.compile( 'two-switch-lab' ) )
    shot( page, outdir, 'gui-overview%s.png' % suffix )

    original = page.locator( '#editor' ).input_value()
    broken = original.replace( 'switch: ovs ', 'switch: cisco ' ).replace(
        '  - [h3, s2]', '  - [h3, s9]' )
    page.locator( '#editor' ).fill( broken )
    expect( page.locator( '#issues li' ) ).to_have_count( 2 )
    expect( page.locator( '#issues' ) ).to_contain_text( 'use one of' )
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
    expect( page.locator( '#graph circle.halo[visibility=visible]' ) ) \
        .to_have_count( 3 )

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


def run( browser, url, token, outdir, scheme, network ):
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
                run( browser, url.rstrip( '/' ), token, outdir, scheme,
                     network )
        finally:
            browser.close()
    print( 'mn-gui browser test passed' )


if __name__ == '__main__':
    main()
