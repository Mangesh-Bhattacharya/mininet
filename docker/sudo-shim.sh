#!/bin/sh
# Containers already run as root, but tutorials say "sudo mn ...".
# This shim drops sudo's own options and runs the command directly.
while [ "$#" -gt 0 ]; do
    case "$1" in
        --) shift; break;;
        -u|-g|-h|-p|-C|-D|-R|-T|-U) shift 2;;
        -*) shift;;
        *) break;;
    esac
done
[ "$#" -gt 0 ] || exec bash
exec "$@"
