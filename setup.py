#!/usr/bin/env python3

"Setuptools params"

from setuptools import setup
from os.path import join

# Get version number from source tree
import sys
sys.path.append( '.' )
from mininet.net import VERSION

scripts = [ join( 'bin', filename ) for filename in
            [ 'mn', 'mn-doctor', 'mn-config', 'mn-gui' ] ]

modname = distname = 'mininet'

setup(
    name=distname,
    version=VERSION,
    description='Process-based OpenFlow emulator',
    author='Bob Lantz',
    author_email='rlantz@cs.stanford.edu',
    packages=[ 'mininet', 'mininet.examples' ],
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
)
