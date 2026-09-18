# Security policy

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through
[GitHub's private vulnerability reporting](https://github.com/Mangesh-Bhattacharya/mininet/security/advisories/new)
with steps to reproduce, the affected version or image tag, and the
output of `sudo mn-doctor --json`.

You'll get an acknowledgement within 7 days. Fixes for confirmed issues
are released as soon as they're ready, and the report is credited in the
advisory unless you prefer otherwise. Vulnerabilities in Mininet's core
that also affect upstream are reported to
[mininet/mininet](https://github.com/mininet/mininet) as well.

## Supported versions

| Version | Supported |
|---------|-----------|
| `main` branch and the `latest` / `full` images | Yes - patched weekly |
| Weekly dated images (`YYYYMMDD`) | The newest one only |
| Upstream Mininet releases (2.3.x and older) and old VM images | No - use this fork or its images |

Always run the newest image: `docker pull ghcr.io/mangesh-bhattacharya/mininet:latest`.

## How this project stays patched

Security updates are automated so nothing is left behind, and every
update must pass the full test suite before it is used.

| When | What happens | Where |
|------|--------------|-------|
| Every Monday 04:00 UTC | The Docker images are rebuilt from the newest Ubuntu 24.04 base **without cache**, installing every pending Ubuntu security update, then tested, scanned and republished (`latest`, `full` and a dated tag) | [`docker.yml`](.github/workflows/docker.yml) |
| Every Monday 05:00 UTC | Dependabot opens pull requests for new versions of every GitHub Action, the base image digest and the Python packages | [`dependabot.yml`](.github/dependabot.yml) |
| Every Monday 05:00 UTC, and every push | CodeQL (Python, JavaScript, C, workflows), `pip-audit` and a Trivy scan of the repository run again, so newly published vulnerabilities in unchanged code are found | [`security.yml`](.github/workflows/security.yml) |
| Every Monday 06:00 UTC | The full test suite runs on current runner images | [`tests.yml`](.github/workflows/tests.yml) |
| As soon as an advisory is published | Dependabot security updates open a fix PR immediately (not only on Mondays) | repository settings |
| Every pull request | Dependency review blocks new dependencies with known vulnerabilities (moderate or worse) | [`security.yml`](.github/workflows/security.yml) |

### Build and release safeguards

- **Images are scanned before publishing.** A fixable HIGH or CRITICAL
  vulnerability in an image fails the build, so it is never published.
  Scan results are also uploaded to the repository's Security tab.
- **Images are signed and traceable.** Every published image is signed
  with [Sigstore cosign](https://docs.sigstore.dev/) (keyless, tied to
  this repository's workflow) and carries an SBOM and SLSA build
  provenance.
- **Pinned supply chain.** Every GitHub Action is pinned to a full commit
  SHA (tags can be moved by an attacker; SHAs can't), the base image is
  pinned by digest, and Python packages are pinned to exact versions.
  Dependabot updates all of them weekly.
- **Least privilege in CI.** Workflows default to read-only tokens, jobs
  request only the permissions they need, and checkouts don't keep
  credentials.

### Verify an image before you run it

```bash
cosign verify ghcr.io/mangesh-bhattacharya/mininet:latest \
  --certificate-identity-regexp '^https://github.com/Mangesh-Bhattacharya/mininet/\.github/workflows/docker\.yml@' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Security model

Mininet is a network **emulator for labs and research**. It needs root
on a Linux kernel, so treat the machine or VM that runs it as a lab
machine.

- **Root and `--privileged`.** Mininet creates network namespaces,
  virtual interfaces and Open vSwitch bridges, which requires root (and
  `docker run --privileged` in containers). A privileged container can
  affect its host, so only run images you trust - ideally the signed
  images above - and prefer a VM or Docker Desktop's VM on shared
  machines.
- **Emulated hosts are not isolated from each other's filesystems.**
  Mininet hosts share the machine's file system and run as root. Don't
  run untrusted software inside them.
- **The browser GUI (`mn-gui`)** gives root command execution inside the
  emulated hosts to anyone with its access token. It listens on
  `127.0.0.1` by default and is protected by a random token, Host-header
  checks against DNS rebinding, CSRF-resistant JSON-only API calls and a
  strict Content-Security-Policy; see [docs/gui.md](docs/gui.md#security).
  Publish its port to `127.0.0.1` only and use SSH tunnels for remote
  access.
- **Lab configuration programs** (Python, C, C++, C#, Java, Ruby, COBOL)
  are code. `mn-config` runs them in a scratch directory as the user who
  invoked `sudo`, never as root, but you should still only run configs
  you wrote or trust. YAML and JSON configs are data and are parsed
  safely.

## Maintainer checklist

Automation opens the pull requests; a maintainer merges them:

1. Every Monday, review and merge the Dependabot PRs once CI is green.
2. Check the Security tab for new code-scanning and Dependabot alerts.
3. If the weekly image build fails its vulnerability scan, update the
   affected package (or wait for Ubuntu's fix and re-run the workflow);
   the previous, still-signed image stays published meanwhile.

Repository settings that must stay enabled (Settings -> Code security):
Dependabot alerts, Dependabot security updates, secret scanning with
push protection, code scanning, and private vulnerability reporting.
