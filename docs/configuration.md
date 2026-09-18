# Lab configuration files

A **lab configuration** describes a Mininet network (hosts, switches,
links, link speeds and delays) and what to do once it's running
(commands and tests). You write it once, check it, then run it from the
command line (`mn-config`) or the browser GUI (`mn-gui`).

You can write it in the language you're most comfortable with:

| Language | File | Needs | Kind |
|----------|------|-------|------|
| **YAML** (recommended) | `lab.yaml` | nothing extra | data |
| JSON | `lab.json` | nothing | data |
| Python | `lab.py` | `python3` | program |
| C | `lab.c` | `gcc` | program |
| C++ | `lab.cpp` | `g++` | program |
| C# | `lab.cs` | .NET SDK 6+ (`dotnet`) | program |
| Java | `Lab.java` | JDK 11+ (`java`) | program |
| Ruby | `lab.rb` | `ruby` | program |
| COBOL | `lab.cob` | GnuCOBOL 3 (`cobc`) | program |

**Data** files are read directly. **Programs** print the configuration as
JSON; `mn-config` compiles and runs them for you. Every language produces
exactly the same configuration and goes through the same checks, so pick
YAML unless you want loops or calculations, or your course uses one of
the other languages.

> Which tools are installed? Run `mn-config languages`. The standard
> Docker image includes Python, C, C++ and Ruby; the `full` image adds
> Java, C# and COBOL.

## Quick start

```bash
mn-config init --lang yaml         # writes lab.yaml (or --lang c, java, cobol, ...)
nano lab.yaml                      # edit it; the comments explain every setting
mn-config validate lab.yaml        # check it - no root needed
sudo mn-config run lab.yaml        # start it: runs commands and tests, then the CLI
```

Or in the browser, with a live topology drawing and instant checking:

```bash
sudo mn-gui --config lab.yaml      # creates lab.yaml if it doesn't exist
```

See [gui.md](gui.md). In the Docker container, drop `sudo`.

## What to edit, and what not to

Every setting belongs to one of three groups. The starter files mark them
with `[EDIT]`, `[ADVANCED]` and `[FIXED]`, and `mn-config schema` prints
this list too.

### Edit freely - this is your lab

| Setting | Meaning | Example |
|---------|---------|---------|
| `name` | Name shown in the GUI and logs | `routing-lab-3` |
| `description` | Free text | |
| `network.controller` | `default` (Mininet's built-in learning switch controller), `remote` (your own: Ryu, ONOS, POX, OpenDaylight...) or `none` | `remote` |
| `network.controller_ip`, `network.controller_port` | Where your remote controller listens | `127.0.0.1`, `6653` |
| `network.switch` | `ovs` (Open vSwitch, talks OpenFlow to the controller), `ovsbr` (Open vSwitch as a plain learning bridge), `lxbr` (Linux bridge), `user` (reference switch) | `ovs` |
| `topology.type` | A built-in topology: `minimal`, `single`, `linear` or `tree` | `tree` |
| `topology.hosts`, `.switches`, `.depth`, `.fanout` | Size of the built-in topology | `depth: 2` |
| `topology.link` | Shaping applied to every link | `{ bw: 10, delay: 5ms }` |
| `hosts[].name`, `hosts[].ip` | Your hosts | `h1`, `10.0.0.1/24` |
| `switches[].name` | Your switches | `s1` |
| `links[]` | `[a, b]`, or `{from, to, bw, delay, loss}` | `{ from: s1, to: s2, bw: 10 }` |
| `links[].bw` | Bandwidth limit, Mbit/s (0.1-1000) | `100` |
| `links[].delay` | One-way delay | `5ms`, `100us`, `1s` |
| `links[].loss` | Packet loss, percent | `1` |
| `run[]` | Commands after start: `"<node> <command>"` | `"h1 python3 -m http.server 80 &"` |
| `tests[]` | `pingall` and/or `iperf` | `[pingall]` |
| `gui.port` | Port for `mn-gui` | `8080` |

### Advanced - change only if you know why

| Setting | Default | Why you'd change it |
|---------|---------|---------------------|
| `network.datapath` | `auto` | Force `kernel` or `user` Open vSwitch datapath. `auto` already picks `user` on Docker Desktop and WSL, where the kernel module is missing. |
| `network.ip_base` | `10.0.0.0/8` | Address range for hosts that have no `ip`. |
| `network.auto_arp` | `true` | `false` if your lab is *about* ARP. |
| `network.auto_mac` | `true` | `false` for random MAC addresses. |
| `hosts[].mac` | automatic | Fixed MAC address. |
| `hosts[].gateway` | none | Default route, for routing labs. |
| `switches[].dpid` | from the name | OpenFlow datapath ID (quote it: `"000000000000000a"`). |
| `switches[].protocols` | OVS default | e.g. `OpenFlow13` for controllers that need it. |
| `links[].max_queue` | kernel default | Queue length in packets (buffer-bloat labs). |

### Do not edit

| Setting | Why |
|---------|-----|
| `version: 1` | Identifies the file format. |
| The JSON-printing code at the bottom of the program templates (marked `[FIXED]`) | `mn-config` reads exactly that output. |

### Rules the checker enforces

- Names: a letter then up to 9 letters or digits (`h1`, `web2`) - Linux
  limits interface names like `web2-eth0` to 15 characters.
- Switch names contain a number (`s1`, `core1`) unless you give a `dpid`.
- Every name is unique; every link end exists; no link from a node to
  itself; no duplicate IP addresses.
- Use a built-in `topology` **or** `hosts`/`switches`/`links`, not both.
- `controller: none` needs `switch: ovsbr` or `lxbr` (an OpenFlow switch
  without a controller forwards nothing).
- `run` commands start with a node name that exists.

Mistakes are reported all at once, with a hint:

```text
$ mn-config validate lab.yaml
Configuration problems:
  - netwrok: unknown setting
    hint: did you mean "network"?
  - switches.core.dpid: must be up to 16 hex digits, quoted
    hint: e.g. dpid: "0000000000000001" (quotes stop YAML reading it as a number)
  - links[0].to: unknown node 's9'
    hint: define it under hosts or switches first
```

## Examples

### YAML: a tree with slow links

```yaml
version: 1
name: tree-lab
topology:
  type: tree
  depth: 2
  fanout: 3
  link: { bw: 10, delay: 2ms }
tests: [pingall, iperf]
```

### YAML: your own controller

```yaml
version: 1
name: ryu-lab
network:
  controller: remote
  controller_ip: 127.0.0.1
  controller_port: 6653
switches:
  - { name: s1, protocols: OpenFlow13 }
hosts:
  - { name: h1, ip: 10.0.0.1/24 }
  - { name: h2, ip: 10.0.0.2/24 }
links: [[h1, s1], [h2, s1]]
```

### The same lab in every language

`mn-config init --lang <language>` writes a starter file with three hosts,
two switches and a 10 Mbit/s, 5 ms link between the switches. Compare
them side by side in [`mininet/templates/`](../mininet/templates/):
[YAML](../mininet/templates/lab.yaml) &middot;
[JSON](../mininet/templates/lab.json) &middot;
[Python](../mininet/templates/lab.py) &middot;
[C](../mininet/templates/lab.c) &middot;
[C++](../mininet/templates/lab.cpp) &middot;
[C#](../mininet/templates/lab.cs) &middot;
[Java](../mininet/templates/Lab.java) &middot;
[Ruby](../mininet/templates/lab.rb) &middot;
[COBOL](../mininet/templates/lab.cob)

### Writing a program config

A program config can compute anything, as long as it prints one JSON
object with the settings above. For example, 20 hosts in Ruby:

```ruby
require 'json'
hosts = (1..20).map { |i| { name: "h#{i}", ip: "10.0.0.#{i}/24" } }
puts JSON.generate(version: 1, name: 'big-lab',
                   hosts: hosts, switches: [{ name: 's1' }],
                   links: hosts.map { |h| [h[:name], 's1'] })
```

How `mn-config` runs each language:

| Language | Build | Run |
|----------|-------|-----|
| Python | - | `python3 lab.py` |
| C | `gcc -std=c99 -O1` | the binary |
| C++ | `g++ -std=c++17 -O1` | the binary |
| C# | `dotnet build` (a project file is generated) | `dotnet labconfig.dll` |
| Java | - | `java Lab.java` (single-file source launch) |
| Ruby | - | `ruby lab.rb` |
| COBOL | `cobc -x -free` (free format) | the binary |

Programs run in a temporary copy of your file, with a 5-minute limit for
compiling and 1 minute for running. **When you use `sudo`, the program
runs as you, not as root** (Mininet itself still needs root). Still,
only run config programs you wrote or trust - just like any other
program.

Want the full Mininet Python API instead (custom node classes, scripted
experiments, measurements)? Write a normal Mininet script; see
[getting-started.md](getting-started.md#5-the-python-api) and `examples/`.

## Installing language toolchains

YAML, JSON, Python, C and C++ work out of the box after `install.sh` and
in the Docker image.

| Language | Ubuntu / Debian / WSL | Docker |
|----------|------------------------|--------|
| Ruby | `sudo apt install ruby` | included |
| Java | `sudo apt install default-jdk-headless` | `:full` image |
| C# | `sudo apt install dotnet-sdk-8.0` (Ubuntu 24.04; elsewhere see [Microsoft's instructions](https://learn.microsoft.com/dotnet/core/install/linux)) | `:full` image |
| COBOL | `sudo apt install gnucobol` | `:full` image |

```bash
docker run --rm -it --privileged ghcr.io/mangesh-bhattacharya/mininet:full
```

## Command reference

| Command | Does |
|---------|------|
| `mn-config init [--lang L] [-o FILE] [--force]` | Write a commented starter config |
| `mn-config validate FILE` | Check a config and summarize it (no root) |
| `mn-config show FILE` | Print the checked config, with defaults filled in, as JSON |
| `sudo mn-config run FILE [--no-cli] [-v debug]` | Start the network, run `run` commands and `tests`, open the Mininet CLI. Exit code 1 if a test fails. |
| `mn-config languages` | Which languages are ready on this machine |
| `mn-config schema` | Every setting, grouped by edit freely / advanced / do not edit |

Tests exit non-zero when they fail, so `sudo mn-config run lab.yaml
--no-cli` works in scripts and autograders.
