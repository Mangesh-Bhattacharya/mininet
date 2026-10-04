"""Security & Compliance agent: the single gate between generated content and the outside world.

Controls: kill switch, secret scan, PII scan, URL allowlist, YouTube policy limits,
spam-metadata heuristics, claim screening, publish rate cap, token-file permissions,
OAuth scope least-privilege check, and a hash-chained append-only audit log.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ..config import Config
from ..models import PackageStatus, YouTubePackage

SECRET_PATTERNS = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "oauth_token": re.compile(r"ya29\.[0-9A-Za-z_\-]{20,}"),
    "refresh_token": re.compile(r"1//[0-9A-Za-z_\-]{30,}"),
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "generic_secret": re.compile(r"(?i)(?:secret|token|password|stream[_ -]?key)\s*[:=]\s*\S{8,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
RISKY_CLAIMS = re.compile(
    r"(?i)\b(guaranteed|cures?|heals? (?:cancer|disease)|miracle|get rich|tax[- ]deductible|"
    r"official tax receipt|100% (?:safe|effective))\b")
ALLOWED_SCOPES = {
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",             # needed for liveBroadcasts/playlists
    "https://www.googleapis.com/auth/gmail.readonly",
}
FORBIDDEN_SCOPES = {"https://mail.google.com/", "https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/gmail.send"}


@dataclass
class Finding:
    severity: str      # block | warn
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "detail": self.detail}


class AuditLog:
    """Tamper-evident JSONL: each record embeds sha256 of the previous line."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._prev = self._last_hash()

    def _last_hash(self) -> str:
        if not self.path.exists() or not self.path.stat().st_size:
            return "0" * 64
        last = self.path.read_text().strip().splitlines()[-1]
        return hashlib.sha256(last.encode()).hexdigest()

    def write(self, actor: str, action: str, **fields: object) -> None:
        rec = {"ts": time.time(), "actor": actor, "action": action, "prev": self._prev, **fields}
        line = json.dumps(rec, sort_keys=True, default=str)
        with self.path.open("a") as f:
            f.write(line + "\n")
        self.path.chmod(0o600)
        self._prev = hashlib.sha256(line.encode()).hexdigest()

    def verify(self) -> bool:
        prev = "0" * 64
        for line in self.path.read_text().splitlines():
            if json.loads(line)["prev"] != prev:
                return False
            prev = hashlib.sha256(line.encode()).hexdigest()
        return True


def kill_switch_on(cfg: Config) -> bool:
    return cfg.kill_switch_file.exists()


def scan_text(text: str, cfg: Config, label: str) -> list[Finding]:
    out: list[Finding] = []
    for name, rx in SECRET_PATTERNS.items():
        if rx.search(text):
            out.append(Finding("block", "secret", f"{label}: possible {name}"))
    for m in EMAIL_RE.findall(text):
        if m.lower() not in {c.lower() for c in cfg.allowed_contacts}:
            out.append(Finding("block", "pii_email", f"{label}: unlisted email address"))
    for m in PHONE_RE.findall(text):
        if re.sub(r"\D", "", m) not in {re.sub(r"\D", "", c) for c in cfg.allowed_contacts}:
            out.append(Finding("block", "pii_phone", f"{label}: unlisted phone number"))
    for u in URL_RE.findall(text):
        p = urlparse(u)
        host = (p.hostname or "").removeprefix("www.")
        if p.scheme != "https":
            out.append(Finding("block", "url_scheme", f"{label}: non-https URL {host}"))
        elif not any(host == d or host.endswith("." + d) for d in cfg.all_allowed_domains):
            out.append(Finding("block", "url_domain", f"{label}: domain not allowlisted: {host}"))
    if RISKY_CLAIMS.search(text):
        out.append(Finding("block", "claims", f"{label}: unsubstantiated/risky claim wording"))
    return out


def review_package(pkg: YouTubePackage, cfg: Config, scheduled_today: int = 0) -> list[Finding]:
    f: list[Finding] = []
    if len(pkg.title) > 100 or not pkg.title:
        f.append(Finding("block", "title_len", f"title length {len(pkg.title)}"))
    if len(pkg.description.encode()) > 5000:
        f.append(Finding("block", "desc_len", "description exceeds 5000 bytes"))
    if any(c in pkg.title + pkg.description for c in "<>"):
        f.append(Finding("block", "angle_brackets", "YouTube rejects < >"))
    if sum(len(t) + 1 for t in pkg.tags) > 500:
        f.append(Finding("block", "tags_len", "tags exceed 500 chars"))
    if len(pkg.tags) > 15:
        f.append(Finding("warn", "tag_stuffing", f"{len(pkg.tags)} tags (>15 looks like spam)"))
    if len(set(re.findall(r"#\w+", pkg.description))) > 15:
        f.append(Finding("block", "hashtag_spam", "more than 15 hashtags nullifies all hashtags"))
    if pkg.title.isupper() and len(pkg.title) > 12:
        f.append(Finding("warn", "title_caps", "all-caps title"))
    if pkg.thumbnail_path and Path(pkg.thumbnail_path).exists() and Path(pkg.thumbnail_path).stat().st_size > 2_000_000:
        f.append(Finding("block", "thumb_size", "thumbnail > 2MB"))
    elif not pkg.thumbnail_path:
        f.append(Finding("warn", "no_thumbnail", "no thumbnail attached"))
    f += scan_text(pkg.title, cfg, "title") + scan_text(pkg.description, cfg, "description")
    f += scan_text(" ".join(pkg.tags), cfg, "tags")
    for p in pkg.social_posts:
        f += scan_text(p.text, cfg, f"social:{p.platform}")
    if scheduled_today >= cfg.daily_publish_cap:
        f.append(Finding("block", "rate_cap", "daily publish cap reached (YouTube quota guard)"))
    return f


def gate(pkg: YouTubePackage, cfg: Config, audit: AuditLog, scheduled_today: int = 0) -> YouTubePackage:
    findings = review_package(pkg, cfg, scheduled_today)
    pkg.security_findings = [x.to_dict() for x in findings]
    blocked = any(x.severity == "block" for x in findings) or kill_switch_on(cfg)
    pkg.status = PackageStatus.BLOCKED if blocked else PackageStatus.READY
    audit.write("security", "gate", event=pkg.event_id, status=pkg.status.value,
                findings=[x.code for x in findings])
    return pkg


def check_credentials(token_path: Path, scopes: list[str]) -> list[Finding]:
    f: list[Finding] = []
    if token_path.exists():
        mode = stat.S_IMODE(token_path.stat().st_mode)
        if mode & 0o077:
            f.append(Finding("block", "token_perms", f"{token_path} is {oct(mode)}; require 0600"))
    for s in scopes:
        if s in FORBIDDEN_SCOPES:
            f.append(Finding("block", "scope_forbidden", f"over-broad scope {s}"))
        elif s not in ALLOWED_SCOPES:
            f.append(Finding("warn", "scope_unknown", f"unreviewed scope {s}"))
    return f
