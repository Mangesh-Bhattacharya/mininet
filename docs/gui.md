# Mininet Lab GUI (`mn-gui`)

`mn-gui` is a browser GUI for [lab configurations](configuration.md). It
runs wherever Mininet runs (Linux, WSL 2, a VM or the Docker container)
and you use it from any browser, including one on the Windows or macOS
machine hosting that container or VM.

- **Topology**: a live drawing of hosts, switches, links (with bandwidth
  and delay) and the controller.
- **Configuration**: edit YAML/JSON configs with instant checking; errors
  come with hints and Save stays disabled until the file is valid.
- **Start / Stop / Ping all**: run the network and see which hosts reach
  each other as a matrix.
- **Console**: run commands on any node (`ip addr`, `ping`, `curl`...)
  and measure bandwidth with iperf.
- **Guide**: every setting, grouped by *edit freely*, *advanced* and *do
  not edit*.

Configs written as programs (Python, C, C++, C#, Java, Ruby, COBOL) are
shown read-only: edit them in your editor, then press **Reload from
disk**.

MiniEdit (`examples/miniedit.py`), Mininet's original drag-and-drop
editor, is still included for Linux desktops and WSLg.

## Start it

### Linux or WSL 2

```bash
sudo mn-gui --config lab.yaml
```

It prints a URL containing your access token:

```text
*** Open this URL in your browser (it contains your access token):

    http://localhost:8080/#token=Xq3...
```

Open it. On WSL 2, open it in your Windows browser - `localhost` is
forwarded automatically. If `lab.yaml` doesn't exist it is created from
the starter template. Without `sudo` you can edit and validate, but not
start networks.

### Docker (Windows, macOS, Linux)

From a clone of this repository:

```bash
scripts/mininet-docker.sh --gui          # Windows: .\scripts\mininet-docker.ps1 -Gui
```

This publishes the GUI on `127.0.0.1:8080` and edits `lab.yaml` in your
current directory. Use `--port 9000` / `-Port 9000` for another port.

Without the repository:

```bash
docker run --rm -it --privileged -p 127.0.0.1:8080:8080 \
  -v "$PWD:/workspace" ghcr.io/mangesh-bhattacharya/mininet \
  mn-gui --config /workspace/lab.yaml
```

(PowerShell: replace `$PWD` with `${PWD}` and `\` with `` ` ``.)

Or with Compose: `docker compose up gui`, then `docker compose logs gui`
for the URL.

### A virtual machine

Keep the GUI on the VM's loopback and reach it through SSH, which also
encrypts the connection:

```bash
# on your computer
vagrant ssh -- -L 8080:localhost:8080          # Vagrant
ssh -L 8080:localhost:8080 ubuntu@<vm-address> # Multipass, UTM, any VM
# then, inside the VM
sudo mn-gui --config lab.yaml
```

and open the printed URL on your computer.

## Options

| Option | Default | Meaning |
|--------|---------|---------|
| `--config FILE`, `-c` | read-only example | Lab configuration to edit and run (created from the template if missing) |
| `--port N`, `-p` | `gui.port` from the config, else 8080 | Port to listen on |
| `--host ADDR` | `127.0.0.1` (`0.0.0.0` inside the Docker image) | Address to listen on |
| `--allow-host NAME` | - | Extra host name the browser may use, e.g. a VM's DNS name |
| `--verbosity LEVEL`, `-v` | `info` | `debug` logs every request |

Environment: `MININET_GUI_TOKEN` sets the access token (at least 16
characters) instead of a random one - useful for scripts;
`MININET_GUI_HOST` sets the default for `--host`.

## Security

Anyone who can use the GUI can run commands **as root** inside the
emulated hosts, exactly like the Mininet CLI. The GUI is designed so
that only you can:

| Protection | What it stops |
|------------|---------------|
| Listens on `127.0.0.1` by default; Docker ports are published to `127.0.0.1` only | Other machines on your network (Wi-Fi, campus LAN) reaching it |
| Random 192-bit access token on every API call, compared in constant time | Other users and programs on the same machine |
| Token passed in the URL `#fragment` and kept in session storage | The token leaking into server logs, proxies or `Referer` headers |
| `Host` header must be `localhost`/`127.0.0.1`/`[::1]` (or `--allow-host`) | DNS-rebinding attacks from web pages you visit |
| API accepts only JSON with an `Authorization` header, sends no CORS headers | Other web sites posting forms or scripts to it (CSRF) |
| Strict `Content-Security-Policy`, no inline or third-party scripts, all output inserted as text | Cross-site scripting through node output or config text |
| 1 MB request limit, 30 s command timeout, 64 KB output limit | Runaway requests and commands |
| YAML parsed with `safe_load` | YAML files creating Python objects |
| Config programs run as the user who ran `sudo` | Config programs gaining root |
| Standard library only (no web framework) | Third-party dependency vulnerabilities |

Don't use `--host 0.0.0.0` on a shared network. To use the GUI from
another machine, use an SSH tunnel (above) instead. Report security
problems as described in [SECURITY.md](../SECURITY.md).

## API

The GUI is a thin client over a small JSON API that you can script too.
Every call needs `Authorization: Bearer <token>`; `POST` bodies are JSON.

| Call | Does |
|------|------|
| `GET /api/status` | Running?, root?, file, language, hosts, nodes, config issues |
| `GET /api/config`, `GET /api/graph`, `GET /api/schema` | File text; nodes and links; setting reference |
| `POST /api/validate {text}` | Check text without saving |
| `POST /api/save {text}` | Check and save (YAML/JSON only) |
| `POST /api/reload` | Re-read the file (network must be stopped) |
| `POST /api/start`, `POST /api/stop` | Start (runs `run` commands) or stop the network |
| `POST /api/pingall` | Reachability matrix and loss |
| `POST /api/iperf {src, dst}` | TCP bandwidth between two hosts |
| `POST /api/exec {node, command}` | Run a shell command on a node |

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status
```
