# Getting started with Mininet

This walkthrough takes about 15 minutes. It assumes Mininet is installed
([Linux](install/linux.md), [Windows](install/windows.md),
[macOS](install/macos.md), [Docker](install/docker.md) or a
[VM](install/virtual-machines.md)) and that `sudo mn-doctor` reports no
failures.

Inside the Docker container you are already root: `sudo` is optional.

## 1. Your first network

```bash
sudo mn
```

This creates the default topology: one OpenFlow switch `s1`, two hosts
`h1` and `h2`, and a controller `c0`. You're now at the Mininet CLI:

```text
mininet> nodes          # list nodes
mininet> net            # show links
mininet> dump           # show node details and IPs
mininet> h1 ifconfig    # run any Linux command on a host
mininet> h1 ping -c 3 h2
mininet> pingall        # test connectivity between all hosts
mininet> iperf          # measure TCP throughput between two hosts
mininet> exit
```

Each host is a shell in its own network namespace, so `h1 ps`, `h1 ip
route` and `h1 python3 -m http.server 80 &` all work as they would on a
real machine.

## 2. Topologies

```bash
sudo mn --topo single,4                 # one switch, 4 hosts
sudo mn --topo linear,4                 # 4 switches in a line, 1 host each
sudo mn --topo tree,depth=2,fanout=3    # tree of switches, 9 hosts
sudo mn --topo tree,2,2 --test pingall  # build, test and exit
```

## 3. Link properties

Emulate slow or lossy links with `--link tc` (needs `htb`/`netem`
support; `mn-doctor` tells you):

```bash
sudo mn --link tc,bw=10,delay=20ms,loss=1
mininet> iperf
mininet> h1 ping -c 5 h2
```

## 4. Switches and controllers

```bash
sudo mn --switch ovsk                          # Open vSwitch (default)
sudo mn --switch ovsbr --controller none       # OVS as a learning bridge
sudo mn --switch lxbr --controller none        # Linux bridge
sudo mn --controller remote,ip=127.0.0.1,port=6653   # your own controller
mininet> sh ovs-ofctl dump-flows s1            # inspect OpenFlow rules
```

## 5. The Python API

Save this as `mytopo.py` (with Docker, save it in the directory you
started the launcher from; it appears in `/workspace`):

```python
#!/usr/bin/env python3
from mininet.net import Mininet
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


class TwoSwitchTopo(Topo):
    "h1 - s1 ==(10 Mbit/s, 5 ms)== s2 - h2"

    def build(self):
        h1, h2 = self.addHost('h1'), self.addHost('h2')
        s1, s2 = self.addSwitch('s1'), self.addSwitch('s2')
        self.addLink(h1, s1)
        self.addLink(s1, s2, bw=10, delay='5ms')
        self.addLink(s2, h2)


if __name__ == '__main__':
    setLogLevel('info')
    net = Mininet(topo=TwoSwitchTopo(), link=TCLink)
    net.start()
    net.pingAll()
    h1, h2 = net.get('h1', 'h2')
    print(h1.cmd('ping -c 3', h2.IP()))
    CLI(net)          # remove this line for a non-interactive script
    net.stop()
```

```bash
sudo python3 mytopo.py
```

The same class can be loaded by `mn`:

```bash
sudo mn --custom mytopo.py --topo twoswitch   # after adding: topos = {'twoswitch': TwoSwitchTopo}
```

## 6. Lab configuration files and the browser GUI

Instead of long `mn` command lines or Python, you can describe a lab in
a file - YAML, JSON, Python, C, C++, C#, Java, Ruby or COBOL - and run
it:

```bash
mn-config init --lang yaml         # commented starter file: lab.yaml
mn-config validate lab.yaml        # check it
sudo mn-config run lab.yaml        # run it
sudo mn-gui --config lab.yaml      # or edit and run it in your browser
```

The starter file marks every setting as *edit freely*, *advanced* or
*do not edit*. See [configuration.md](configuration.md) and
[gui.md](gui.md).

## 7. Where to go next

- `examples/` has 40+ scripts: NAT, Linux routers, CPU limits, multiple
  controllers, bandwidth tests, and the MiniEdit GUI (`examples/miniedit.py`).
- The upstream [walkthrough](http://mininet.org/walkthrough/) and
  [Python API introduction](https://github.com/mininet/mininet/wiki/Introduction-to-Mininet).
- If anything goes wrong: `sudo mn -c`, then
  [troubleshooting](troubleshooting.md).
