#!/usr/bin/env python3

"""
Doxygen input filter for Mininet's docstring style.

Mininet documents parameters as "name: description" and results as
"returns: description". This filter turns them into doxygen @param and
@returns commands and makes one-line "docstrings" triple-quoted, then
writes the result to standard output for doxygen (INPUT_FILTER in
doc/doxygen.cfg). doxygen parses Python docstrings itself, so the old
doxypy (Python 2) post-processing step is no longer needed.

Usage: util/doxify.py file.py > filtered.py
"""

import re
import sys

spaces = re.compile( r'\s+' )
singleLineExp = re.compile( r'\s+"([^"]+)"' )
commentStartExp = re.compile( r'\s+"""' )
commentEndExp = re.compile( r'"""$' )


class Filter( object ):
    "Line-by-line docstring converter"

    def __init__( self ):
        self.comment = False

    @staticmethod
    def fixParam( line ):
        "Change foo: bar to @param foo bar"
        result = re.sub( r'(\w+):', r'@param \1', line )
        return re.sub( r'   @', r'@', result )

    @staticmethod
    def fixReturns( line ):
        "Change returns: foo to @returns foo"
        return re.sub( 'returns:', r'@returns', line )

    def fixLine( self, line ):
        "Convert one line"
        if not spaces.match( line ):
            return line
        if singleLineExp.match( line ):
            return re.sub( '"', '"""', line )
        if commentStartExp.match( line ):
            self.comment = True
        if self.comment:
            line = self.fixParam( self.fixReturns( line ) )
        if commentEndExp.search( line.rstrip() ):
            self.comment = False
        return line


def test():
    "Test transformations"
    f = Filter()
    assert f.fixLine( ' "foo"' ) == ' """foo"""'
    assert Filter.fixParam( 'foo: bar' ) == '@param foo bar'
    assert commentStartExp.match( '   """foo"""' )


def main( argv ):
    "Filter argv[1] to stdout"
    if len( argv ) != 2:
        sys.stderr.write( __doc__ )
        return 2
    converter = Filter()
    with open( argv[ 1 ], encoding='utf-8' ) as infile:
        for line in infile:
            sys.stdout.write( converter.fixLine( line ) )
    return 0


if __name__ == '__main__':
    sys.exit( main( sys.argv ) )
