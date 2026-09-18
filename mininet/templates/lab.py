#!/usr/bin/env python3
"""
Mininet lab configuration (Python)

This program builds the lab configuration as a Python dict and prints
it as JSON. Use Python when you want loops or calculations, e.g. to
generate 20 hosts.

  mn-config validate lab.py      check it (no root needed)
  sudo mn-config run lab.py      start the network and open the CLI

[EDIT]      change freely          [ADVANCED] change only if you know why
[FIXED]     do not change

Want the full Mininet Python API instead (custom node classes,
experiments)? Write a normal Mininet script: see examples/.
Reference: docs/configuration.md
"""

import json

# [EDIT] How many hosts to put on each switch
HOSTS_PER_SWITCH = { 's1': 2, 's2': 1 }

hosts, links = [], []
number = 0
for switch, count in HOSTS_PER_SWITCH.items():
    for _ in range( count ):
        number += 1
        name = 'h%d' % number
        hosts.append( { 'name': name, 'ip': '10.0.0.%d/24' % number } )
        links.append( [ name, switch ] )

# [EDIT] The link between the switches: 10 Mbit/s, 5 ms delay
links.append( { 'from': 's1', 'to': 's2', 'bw': 10, 'delay': '5ms' } )

CONFIG = {
    'version': 1,                        # [FIXED]
    'name': 'two-switch-lab',            # [EDIT]
    'network': {
        'controller': 'default',         # [EDIT] default | remote | none
        'switch': 'ovs',                 # [EDIT] ovs | ovsbr | lxbr | user
        'datapath': 'auto',              # [ADVANCED] auto | kernel | user
    },
    'hosts': hosts,
    'switches': [ { 'name': s } for s in HOSTS_PER_SWITCH ],
    'links': links,
    'run': [ 'h1 ip -brief address' ],   # [EDIT] "<node> <command>"
    'tests': [ 'pingall' ],              # [EDIT] pingall | iperf
}

if __name__ == '__main__':
    print( json.dumps( CONFIG, indent=2 ) )  # [FIXED] mn-config reads this
