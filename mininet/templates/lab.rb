# Mininet lab configuration (Ruby)
#
# Edit the hash below. The program prints the configuration as JSON;
# mn-config runs it with ruby and reads that output.
#
#   mn-config validate lab.rb      check it (no root needed)
#   sudo mn-config run lab.rb      start the network and open the CLI
#
# [EDIT] change freely   [ADVANCED] only if you know why   [FIXED] don't
# Reference: docs/configuration.md

require 'json'

config = {
  version: 1,                      # [FIXED]
  name: 'two-switch-lab',          # [EDIT]
  network: {
    controller: 'default',         # [EDIT] default | remote | none
    switch: 'ovs',                 # [EDIT] ovs | ovsbr | lxbr | user
    datapath: 'auto'               # [ADVANCED] auto | kernel | user
  },
  # [EDIT] Hosts: name and address/prefix
  hosts: (1..3).map { |i| { name: "h#{i}", ip: "10.0.0.#{i}/24" } },
  # [EDIT] Switch names must contain a number
  switches: [{ name: 's1' }, { name: 's2' }],
  # [EDIT] Links; the last one is 10 Mbit/s with 5 ms delay
  links: [
    %w[h1 s1],
    %w[h2 s1],
    %w[h3 s2],
    { from: 's1', to: 's2', bw: 10, delay: '5ms' }
  ],
  run: ['h1 ip -brief address'],   # [EDIT] "<node> <command>"
  tests: ['pingall']               # [EDIT] pingall | iperf
}

puts JSON.pretty_generate(config)  # [FIXED] mn-config reads this
