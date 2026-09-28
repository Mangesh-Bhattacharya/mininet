#!/usr/bin/env python3

"Setuptools params"

import re
from os.path import dirname, join

from setuptools import setup

here = dirname( __file__ ) or '.'


def readVersion():
    """Read the version from the source tree. We read the file instead of
       importing mininet.net, which only imports on Linux, so that the
       package also builds and installs on Windows and macOS (where
       mn-config and mn-gui work but the emulator itself does not)."""
    source = join( here, 'mininet', 'net.py' )
    with open( source, encoding='utf-8' ) as f:
        found = re.search( r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M )
    if not found:
        raise RuntimeError( 'no VERSION in %s' % source )
    return found.group( 1 )


VERSION = readVersion()

# mn is the emulator's own launcher and stays a plain script. The lab
# tools are installed as entry points instead, so that pip also creates
# the .exe wrappers Windows needs to run them by name.
scripts = [ join( 'bin', 'mn' ) ]

consoleScripts = [ 'mn-doctor = mininet.doctor:main',
                   'mn-config = mininet.labconfig:main',
                   'mn-gui = mininet.webgui:main' ]

modname = distname = 'mininet'

setup(
    name=distname,
    version=VERSION,
    description='Process-based OpenFlow emulator',
    author='Bob Lantz',
    author_email='rlantz@cs.stanford.edu',
    packages=[ 'mininet', 'mininet.examples' ],
    # mininet/examples is a symlink to examples/, which Windows clones
    # check out as a plain file; point at the real directory instead so
    # the package builds from a clone on every operating system
    package_dir={ 'mininet.examples': 'examples' },
    package_data={ 'mininet': [ 'templates/*', 'webgui_static/*' ] },
    long_description="""
        Mininet is a network emulator which uses lightweight
        virtualization to create virtual networks for rapid
        prototyping of Software-Defined Network (SDN) designs
        using OpenFlow. http://mininet.org
        """,
    classifiers=[
          "License :: OSI Approved :: BSD License",
          "Programming Language :: Python",
          "Development Status :: 5 - Production/Stable",
          "Intended Audience :: Developers",
          "Topic :: System :: Emulators",
    ],
    keywords='networking emulator protocol Internet OpenFlow SDN',
    license='BSD',
    install_requires=[
        'setuptools'
    ],
    # YAML configuration files (mn-config, mn-gui); JSON and the other
    # languages work without it
    extras_require={ 'yaml': [ 'PyYAML' ] },
    scripts=scripts,
    entry_points={ 'console_scripts': consoleScripts },
)
