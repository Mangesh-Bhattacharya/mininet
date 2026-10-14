#!/usr/bin/env python3

"""
Map this project's security controls onto MITRE ATT&CK techniques and
report what the latest scans found.

  attack-report.py --doc                 print docs/security/attack-coverage.md
  attack-report.py --summary [results]   print the audit report for a run

"results" are the files the fortnightly audit produces; every one is
optional, and a control whose evidence is missing is reported as "not
run" rather than as a pass:

  --trivy FILE.sarif     Trivy image/filesystem scan (SARIF)
  --osv FILE.json        OSV-Scanner dependency scan (JSON)
  --clamav FILE.txt      clamscan output
  --gitleaks FILE.json   gitleaks report

Exit status is 1 when any evidence shows findings, so the workflow can
fail and open an issue.
"""

import argparse
import json
import os
import re
import sys

# Controls, in ATT&CK order. "evidence" names the scan that proves the
# control still works; controls without one are design properties that
# code review and CodeQL keep honest.
CONTROLS = [
    { 'technique': 'T1190',
      'name': 'Exploit Public-Facing Application',
      'risk': 'mn-gui serves HTTP; a flaw in it would be reachable from '
              'the browser, or from the network if it were exposed.',
      'control': 'Binds to 127.0.0.1 by default and Docker publishes to '
                 '127.0.0.1 only; Host header allow-list stops DNS '
                 'rebinding; JSON-only API with no CORS; strict '
                 'Content-Security-Policy; 1 MB body, 30 s command and '
                 '64 KB output limits; standard library only.',
      'evidence': 'codeql' },
    { 'technique': 'T1195.001',
      'name': 'Compromise Software Dependencies and Development Tools',
      'risk': 'A vulnerable or malicious dependency (PyPI, apt, a GitHub '
              'Action) reaches everyone who installs the project.',
      'control': 'Dependabot opens updates weekly; pip-audit and '
                 'OSV-Scanner check every dependency; dependency review '
                 'blocks vulnerable additions in pull requests; Actions '
                 'are pinned to commit SHAs and the base image to a '
                 'digest.',
      'evidence': 'osv' },
    { 'technique': 'T1195.002',
      'name': 'Compromise Software Supply Chain',
      'risk': 'Someone publishes an image or a release that looks like '
              'ours.',
      'control': 'Images are built in CI from a digest-pinned base, '
                 'signed with cosign (keyless, GitHub OIDC) and '
                 'published with an SBOM and build provenance; releases '
                 'come from tags on master.',
      'evidence': 'trivy' },
    { 'technique': 'T1059',
      'name': 'Command and Scripting Interpreter',
      'risk': 'The GUI and the CLI run commands inside emulated hosts as '
              'root - that is the product, so it has to be gated.',
      'control': 'Every API call needs the 192-bit access token, '
                 'compared in constant time; commands run without a '
                 'shell where possible, with a timeout and an output '
                 'cap; configuration programs run as the user who ran '
                 'sudo, never as root.',
      'evidence': 'codeql' },
    { 'technique': 'T1068',
      'name': 'Exploitation for Privilege Escalation',
      'risk': 'mnexec is setuid root, and Mininet itself runs as root.',
      'control': 'mnexec is built hardened (FORTIFY_SOURCE, stack '
                 'protector, PIE, RELRO/BIND_NOW), opens files with '
                 'O_CLOEXEC and parses its arguments strictly; CodeQL '
                 'scans the C code on every change.',
      'evidence': 'codeql' },
    { 'technique': 'T1105',
      'name': 'Ingress Tool Transfer',
      'risk': 'A file in the repository, or in a published image, '
              'carries malware to the people who install it.',
      'control': 'ClamAV scans the working tree and the image '
                 'filesystem every two weeks with fresh signatures.',
      'evidence': 'clamav' },
    { 'technique': 'T1525',
      'name': 'Implant Internal Image',
      'risk': 'A backdoor is added to the container image.',
      'control': 'Images are rebuilt weekly from scratch with no cache, '
                 'scanned with Trivy (the build fails on fixable '
                 'HIGH/CRITICAL), signed, and ship an SBOM anyone can '
                 'diff.',
      'evidence': 'trivy' },
    { 'technique': 'T1552.001',
      'name': 'Unsecured Credentials: Credentials In Files',
      'risk': 'A token or key is committed by accident.',
      'control': 'gitleaks scans the full history and Trivy scans the '
                 'tree for secrets; the GUI token is generated per run '
                 'and never written to a file.',
      'evidence': 'gitleaks' },
    { 'technique': 'T1078',
      'name': 'Valid Accounts',
      'risk': 'A workflow token or the GUI token is stolen and reused.',
      'control': 'Workflows declare the least privilege they need and '
                 'check out without persisted credentials; the GUI '
                 'token travels in the URL fragment, is kept in session '
                 'storage and never reaches a log, proxy or Referer '
                 'header.',
      'evidence': 'codeql' },
    { 'technique': 'T1562.001',
      'name': 'Impair Defenses: Disable or Modify Tools',
      'risk': 'A change lands on master without the checks running.',
      'control': 'master takes pull requests only, with the test, build '
                 'and scan checks required and force-pushes blocked; '
                 'the workflows themselves are scanned by CodeQL '
                 '(actions) and reviewed by Dependabot.',
      'evidence': None },
    { 'technique': 'T1611',
      'name': 'Escape to Host',
      'risk': 'The container runs --privileged, because the emulator '
              'needs network namespaces and Open vSwitch.',
      'control': 'Documented plainly; the image carries no extra setuid '
                 'binaries, drops the Open vSwitch PKI from the image, '
                 'and is meant for a developer machine or a lab VM, not '
                 'a shared host.',
      'evidence': 'trivy' },
    { 'technique': 'T1565',
      'name': 'Data Manipulation',
      'risk': 'The GUI rewrites the lab file; a crash mid-write could '
              'destroy a student\'s work.',
      'control': 'Saves are atomic (write to a temporary file in the '
                 'same directory, then rename) and keep the original '
                 'owner and mode.',
      'evidence': None },
]

EVIDENCE_NAMES = {
    'osv': 'OSV-Scanner', 'trivy': 'Trivy', 'clamav': 'ClamAV',
    'gitleaks': 'gitleaks', 'codeql': 'CodeQL' }

HEADER = """<!-- Generated by scripts/security/attack-report.py --doc.
     Edit that file, not this one. -->

# Security controls, mapped to MITRE ATT&CK

Every two weeks (and on every change) this project scans itself for
malware, vulnerable dependencies, leaked secrets and insecure code, and
updates what it depends on. This page says *why* each check exists, by
naming the [MITRE ATT&CK](https://attack.mitre.org/) technique it
defends against.

Results appear under the repository's **Security** tab; a failed audit
opens an issue automatically. How to report a problem you find:
[SECURITY.md](../../SECURITY.md).
"""

FOOTER = """
## The schedule

| When | What runs |
|------|-----------|
| Every change (push, pull request) | Unit, install, Docker, GUI browser and packaging tests; CodeQL (Python, JavaScript, C, Actions); Trivy; pip-audit; dependency review; ShellCheck |
| Every week | Dependabot updates (Actions, pip, base image), a no-cache image rebuild with every pending security patch, and the full test matrix |
| Every two weeks | This audit: ClamAV malware scan, OSV-Scanner, gitleaks over the whole history, a Trivy scan of the published image, and this report |
| Immediately | Dependabot security updates, and GitHub security advisories for anything this project depends on |

Updates that pass every check merge themselves; anything that fails
stops and opens an issue instead.
"""


def readJson( path ):
    "Parse a JSON file, or return None if it is missing or empty"
    if not path or not os.path.exists( path ) or not os.path.getsize( path ):
        return None
    with open( path, encoding='utf-8' ) as handle:
        try:
            return json.load( handle )
        except ValueError:
            return None


def countTrivy( path ):
    """Number of findings Trivy reported. A Trivy JSON report is
       counted vulnerability by vulnerability; a SARIF file by its
       results. The audit is given the report of *fixable* problems:
       vulnerabilities Ubuntu has not fixed yet cannot be acted on, so
       they are tracked on the Security tab instead of failing every
       run forever."""
    data = readJson( path )
    if data is None:
        return None
    if 'runs' in data:
        return sum( len( run.get( 'results', [] ) )
                    for run in data.get( 'runs', [] ) )
    return sum( len( result.get( 'Vulnerabilities' ) or [] ) +
                len( result.get( 'Secrets' ) or [] )
                for result in data.get( 'Results' ) or [] )


def countOsv( path ):
    "Number of vulnerable packages OSV-Scanner found"
    data = readJson( path )
    if data is None:
        return None
    total = 0
    for result in data.get( 'results', [] ):
        for package in result.get( 'packages', [] ):
            total += len( package.get( 'vulnerabilities', [] ) )
    return total


def countGitleaks( path ):
    "Number of leaked secrets gitleaks found"
    data = readJson( path )
    if data is None:
        return None
    return len( data ) if isinstance( data, list ) else None


def countClamav( path ):
    "Infected files clamscan reported, over all of its scan summaries"
    if not path or not os.path.exists( path ):
        return None
    with open( path, encoding='utf-8', errors='replace' ) as handle:
        found = re.findall( r'^Infected files:\s*(\d+)', handle.read(),
                            re.M )
    return sum( int( n ) for n in found ) if found else None


def findings( args ):
    "Map each evidence name to a count, or None when it did not run"
    return { 'trivy': countTrivy( args.trivy ),
             'osv': countOsv( args.osv ),
             'clamav': countClamav( args.clamav ),
             'gitleaks': countGitleaks( args.gitleaks ),
             'codeql': None }


def statusOf( control, counts ):
    "A short status for one control"
    key = control[ 'evidence' ]
    if key is None:
        return 'by design'
    if key == 'codeql':
        return 'CodeQL (Security tab)'
    count = counts.get( key )
    if count is None:
        return '%s: not run' % EVIDENCE_NAMES[ key ]
    if count == 0:
        return '%s: clean' % EVIDENCE_NAMES[ key ]
    return '%s: %d finding%s' % ( EVIDENCE_NAMES[ key ], count,
                                  '' if count == 1 else 's' )


def table( counts=None ):
    "The control table as Markdown"
    lines = [ '| Technique | What could go wrong here | How it is '
              'stopped |' + ( ' Latest scan |' if counts else '' ),
              '|---|---|---|' + ( '---|' if counts else '' ) ]
    for control in CONTROLS:
        link = ( '[%s](https://attack.mitre.org/techniques/%s/)' %
                 ( control[ 'technique' ],
                   control[ 'technique' ].replace( '.', '/' ) ) )
        row = '| %s %s | %s | %s |' % ( link, control[ 'name' ],
                                        control[ 'risk' ],
                                        control[ 'control' ] )
        if counts is not None:
            row += ' %s |' % statusOf( control, counts )
        lines.append( row )
    return '\n'.join( lines )


def document():
    "The committed reference page"
    return '%s\n%s\n%s' % ( HEADER, table(), FOOTER )


def summary( args ):
    "The report for one audit run; returns ( text, ok )"
    counts = findings( args )
    bad = { name: count for name, count in counts.items()
            if count not in ( None, 0 ) }
    lines = [ '# Fortnightly security audit', '' ]
    if bad:
        lines.append( '**Findings that need attention:** ' +
                      ', '.join( '%s (%d)' % ( EVIDENCE_NAMES[ name ],
                                               count )
                                 for name, count in sorted(
                                     bad.items() ) ) )
    else:
        lines.append( 'No malware, leaked secrets, vulnerable '
                      'dependencies or fixable image vulnerabilities '
                      'were found.' )
    lines += [ '', table( counts ), '',
               'Vulnerabilities the distribution has not fixed yet are '
               'listed on the Security tab rather than counted here: '
               'there is nothing to update until a patch exists.',
               '', 'Full reference: docs/security/attack-coverage.md' ]
    return '\n'.join( lines ), not bad


def main():
    "Print the reference page or an audit summary"
    parser = argparse.ArgumentParser( description=__doc__ )
    parser.add_argument( '--doc', action='store_true' )
    parser.add_argument( '--summary', action='store_true' )
    parser.add_argument( '--trivy' )
    parser.add_argument( '--osv' )
    parser.add_argument( '--clamav' )
    parser.add_argument( '--gitleaks' )
    args = parser.parse_args()
    if args.doc:
        print( document() )
        return 0
    if not args.summary:
        parser.error( 'use --doc or --summary' )
    text, ok = summary( args )
    print( text )
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit( main() )
