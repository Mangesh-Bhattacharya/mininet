#!/usr/bin/env python3

"""
Tests for mininet.elevate: re-running Mininet's commands as root so
that the person using them does not have to be an administrator.
"""

import os
import unittest
from unittest import mock

from mininet import elevate


class DecisionTests( unittest.TestCase ):
    "When may a command re-run itself as root?"

    def setUp( self ):
        patcher = mock.patch.dict( os.environ, {}, clear=False )
        patcher.start()
        self.addCleanup( patcher.stop )
        os.environ.pop( 'MININET_NO_SUDO', None )

    @staticmethod
    def setUpMachine( root=False, sudoers=True, posix=True, allowed=True ):
        "Patch out the machine: are we root, is the setup there?"
        return [
            mock.patch.object( elevate, 'isRoot', return_value=root ),
            mock.patch.object( os.path, 'exists',
                               lambda p: sudoers and p == elevate.SUDOERS ),
            mock.patch.object( os, 'name', 'posix' if posix else 'nt' ),
            mock.patch.object( elevate, 'allowed', return_value=allowed ),
            mock.patch.object( elevate.shutil, 'which',
                               lambda name: '/usr/bin/' + name ) ]

    def check( self, expected, **machine ):
        "canElevate() with a patched machine"
        patches = self.setUpMachine( **machine )
        for patcher in patches:
            patcher.start()
        try:
            self.assertEqual( elevate.canElevate( [ 'mn' ] ), expected )
        finally:
            for patcher in reversed( patches ):
                patcher.stop()

    def testSetUpMachine( self ):
        "Everything in place: the command re-runs itself as root"
        self.check( True )

    def testAlreadyRoot( self ):
        "Nothing to do when we are already root"
        self.check( False, root=True )

    def testNotSetUp( self ):
        "Without the sudoers file, sudo is never invoked"
        self.check( False, sudoers=False )

    def testSudoRefuses( self ):
        "The file may exist but not cover this user or command"
        self.check( False, allowed=False )

    def testNotPosix( self ):
        "Nothing to elevate to on Windows"
        self.check( False, posix=False )

    def testOptOut( self ):
        "MININET_NO_SUDO=1 switches the whole thing off"
        os.environ[ 'MININET_NO_SUDO' ] = '1'
        self.check( False )


class AdviceTests( unittest.TestCase ):
    "What a machine that cannot run Mininet is told to do instead"

    def testWslPath( self ):
        "A Windows path is given the way WSL will understand it"
        for windows, wsl in (
                ( r'C:\labs\lab.yaml', '/mnt/c/labs/lab.yaml' ),
                ( r'D:\My Labs\a b.yaml', '/mnt/d/My Labs/a b.yaml' ),
                ( 'lab.yaml', 'lab.yaml' ),          # no drive, no change
                ( '/mnt/c/already', '/mnt/c/already' ),
                ( None, 'lab.yaml' ) ):
            self.assertEqual( elevate.wslPath( windows ), wsl )

    def testWindowsIsToldToInstallFirst( self ):
        """The old advice handed over a command that cannot work: a
           Windows install puts nothing inside WSL, so mn-config is not
           there to run."""
        with mock.patch.object( elevate.sys, 'platform', 'win32' ):
            reason, hint = elevate.blocker( path=r'C:\labs\lab.yaml' )
        self.assertIn( 'no Linux kernel', reason )
        self.assertIn( 'install', hint.lower() )
        # The path is the one WSL understands, not the Windows one
        self.assertIn( '/mnt/c/labs/lab.yaml', hint )
        self.assertNotIn( r'C:\labs', hint )
        # and not the one-liner that hangs on a password prompt
        self.assertNotIn( 'wsl sudo', hint )

    def testMacIsNotToldAboutWsl( self ):
        "macOS gets macOS advice"
        with mock.patch.object( elevate.sys, 'platform', 'darwin' ):
            reason, hint = elevate.blocker( path='/tmp/lab.yaml' )
        self.assertIn( 'macOS', reason )
        self.assertNotIn( 'WSL', hint )


class HelperTests( unittest.TestCase ):
    "The pieces canElevate() is built from"

    def testCommandPath( self ):
        "The command sudo is asked about is an absolute path"
        with mock.patch.object( elevate.shutil, 'which',
                                return_value='/usr/local/bin/mn' ):
            self.assertEqual( elevate.commandPath( [ 'mn', '-c' ] ),
                              '/usr/local/bin/mn' )
        # A path stays a path (spelled the way this platform spells it)
        path = os.path.abspath( os.path.join( os.sep, 'opt', 'mn' ) )
        self.assertEqual( elevate.commandPath( [ path ] ), path )

    def testAllowedAsksSudo( self ):
        "allowed() asks sudo instead of parsing its configuration"
        run = mock.Mock( return_value=mock.Mock( returncode=0 ) )
        with mock.patch.object( elevate.shutil, 'which',
                                return_value='/usr/bin/sudo' ), \
                mock.patch.object( elevate.subprocess, 'run', run ):
            self.assertTrue( elevate.allowed( '/usr/bin/mn' ) )
        command = run.call_args[ 0 ][ 0 ]
        self.assertEqual( command[ :3 ],
                          [ '/usr/bin/sudo', '-n', '-l' ] )

    def testAllowedWithoutSudo( self ):
        "No sudo on the machine: nothing to ask"
        with mock.patch.object( elevate.shutil, 'which',
                                return_value=None ):
            self.assertFalse( elevate.allowed( '/usr/bin/mn' ) )

    def testSetupHintNamesTheUser( self ):
        "The hint is a command the reader can copy"
        with mock.patch.dict( os.environ, { 'SUDO_USER': 'alice' } ):
            hint = elevate.setupHint()
        self.assertIn( 'nonroot-setup.sh', hint )
        self.assertIn( 'alice', hint )

    def testElevateRunsSudo( self ):
        "elevate() replaces the process with sudo <command> <args>"
        execv = mock.Mock()
        sudo = os.path.abspath( os.path.join( os.sep, 'usr', 'bin', 'sudo' ) )
        command = os.path.abspath( os.path.join( os.sep, 'usr', 'bin', 'mn' ) )
        with mock.patch.object( elevate, 'canElevate', return_value=True ), \
                mock.patch.object( elevate.shutil, 'which',
                                   return_value=sudo ), \
                mock.patch.object( elevate.os, 'execv', execv ):
            elevate.elevate( [ command, '--test', 'pingall' ] )
        execv.assert_called_once_with(
            sudo, [ sudo, '-n', command, '--test', 'pingall' ] )

    def testElevateDoesNothingWhenItCannot( self ):
        "A machine without the setup carries on unprivileged"
        with mock.patch.object( elevate, 'canElevate', return_value=False ):
            self.assertFalse( elevate.elevate( [ 'mn' ] ) )


if __name__ == '__main__':
    unittest.main()
