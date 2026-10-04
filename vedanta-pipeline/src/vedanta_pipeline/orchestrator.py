"""Orchestrator: coordinates the eight agents; resumable, idempotent, crash-tolerant.

Per tick: scan inbox -> extract -> per-event package build (SEO, packager, thumbnail, social,
scheduler, merch) -> Security gate -> (optional) publish -> go-public flips -> exports + status.
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable

from .agents import extract, ingest, packager, security, seo, social, thumbnail
from .config import Config
from .models import Event, PackageStatus, Visibility, YouTubePackage
from .publish import social_webhook
from .publish.youtube import YouTubePublisher
from .store import Store, sha256_file

log = logging.getLogger("vedanta")
AGENTS = ["Newsletter Scanner", "SEO Optimizer", "YouTube Packager", "Thumbnail Designer",
          "Social Media", "Scheduler", "Merch & Monetize", "Security"]


class Pipeline:
    def __init__(self, cfg: Config, publisher: YouTubePublisher | None = None,
                 clock: Callable[[], datetime] | None = None, autocomplete: bool = False):
        self.cfg, self.publisher = cfg, publisher
        self.now = clock or (lambda: datetime.now(cfg.tz))
        self.store = Store(cfg.state_dir)
        self.audit = security.AuditLog(cfg.state_dir / "audit.jsonl")
        self.ac = seo.Autocomplete(self.store, enabled=autocomplete)
        cfg.out_dir.mkdir(parents=True, exist_ok=True)

    # ---- bookkeeping ----------------------------------------------------------------------
    def _tick(self, agent: str, n: int = 1) -> None:
        k = f"agent:{agent}"
        self.store.set(f"{k}:tasks", str(int(self.store.get(f"{k}:tasks", "0") or 0) + n))
        self.store.set(f"{k}:last_run", self.now().isoformat())

    # ---- stages ---------------------------------------------------------------------------
    def ingest_new(self) -> list[Event]:
        new: list[Event] = []
        for path in ingest.pending_files(self.cfg.inbox_dir):
            sha = sha256_file(path)
            if self.store.seen_newsletter(sha):
                continue
            try:
                text = ingest.read_newsletter(path)
                events = extract.extract(text, self.cfg, self.now().date())
            except Exception as e:  # one bad file must not stop the loop
                log.error("ingest failed for %s: %s", path.name, e)
                self.audit.write("scanner", "ingest_failed", file=path.name, error=type(e).__name__)
                continue
            self.store.add_newsletter(sha, str(path), self.now().strftime("%Y-%m"))
            for ev in events:
                self.store.put_event(ev.id, sha, ev.to_dict())
            self.audit.write("scanner", "ingested", file=path.name, sha=sha[:12], events=len(events))
            self._tick("Newsletter Scanner", len(events) or 1)
            new += events
        return new

    def build_package(self, event: Event, learned=None) -> YouTubePackage:
        now = self.now()
        keywords = seo.research_keywords(event, self.ac); self._tick("SEO Optimizer")
        pkg = packager.build_package(event, self.cfg, keywords, now); self._tick("YouTube Packager")
        self._tick("Merch & Monetize"); self._tick("Scheduler")
        thumb = thumbnail.render(event, self.cfg, self.cfg.out_dir / event.id / "thumbnail.png",
                                 self.cfg.state_dir.parent / "assets")
        pkg.thumbnail_path = str(thumb); self._tick("Thumbnail Designer")
        pkg.social_posts = social.draft(event, pkg, self.cfg, now, learned); self._tick("Social Media")
        return pkg

    def process_events(self) -> int:
        now, todo = self.now(), []
        for d in self.store.events():
            ev = Event.from_dict(d)
            if ev.start <= now or self.store.package(ev.id):
                continue
            todo.append(ev)
        learned = self._learned_slots()
        with ThreadPoolExecutor(max_workers=4) as ex:      # CPU/IO-light, thread-safe agents only
            built = list(ex.map(lambda e: self._safe_build(e, learned), todo))
        for ev, pkg in zip(todo, built):
            if pkg is None:
                continue
            scheduled_today = sum(1 for p in self.store.packages(PackageStatus.SCHEDULED.value))
            pkg = security.gate(pkg, self.cfg, self.audit, scheduled_today)
            self._tick("Security")
            self.store.put_package(ev.id, pkg.status.value, pkg.to_dict())
            self._export(ev, pkg)
        return len(todo)

    def _safe_build(self, ev: Event, learned) -> YouTubePackage | None:
        try:
            return self.build_package(ev, learned)
        except Exception:
            log.error("build failed for %s\n%s", ev.id, traceback.format_exc())
            self.audit.write("pipeline", "build_failed", event=ev.id)
            return None

    def _learned_slots(self):
        if not self.publisher or not self.publisher._yt:
            return None
        try:
            return seo.learn_best_slots(self.publisher.recent_video_stats()) or None
        except Exception:
            return None

    def publish_due(self) -> int:
        if self.cfg.publish_mode != "schedule" or not self.publisher or security.kill_switch_on(self.cfg):
            return 0
        done = 0
        for d in self.store.packages(PackageStatus.READY.value):
            pkg = _pkg_from_dict(d)
            if len(self.store.packages(PackageStatus.SCHEDULED.value)) >= self.cfg.daily_publish_cap:
                break
            try:
                self.publisher.schedule(pkg)
            except Exception as e:
                log.error("publish failed %s: %s", pkg.event_id, e)
                self.audit.write("publisher", "failed", event=pkg.event_id, error=type(e).__name__)
                continue
            self.store.put_package(pkg.event_id, pkg.status.value, pkg.to_dict())
            self.audit.write("publisher", "scheduled", event=pkg.event_id, watch=pkg.links.get("watch"))
            self._export(Event.from_dict(next(e for e in self.store.events() if e["id"] == pkg.event_id)), pkg)
            done += 1
        return done

    def flip_visibility(self) -> int:
        if not self.publisher:
            return 0
        n, now = 0, self.now()
        evs = {e["id"]: Event.from_dict(e) for e in self.store.events()}
        for d in self.store.packages(PackageStatus.SCHEDULED.value):
            pkg = _pkg_from_dict(d)
            vid = pkg.links.get("share", "").rsplit("/", 1)[-1]
            ev = evs.get(pkg.event_id)
            if vid and ev and pkg.visibility != Visibility.PUBLIC and now >= ev.start - _td(self.cfg.go_public_hours_before):
                self.publisher.set_visibility(vid, Visibility.PUBLIC)
                pkg.visibility = Visibility.PUBLIC
                self.store.put_package(pkg.event_id, pkg.status.value, pkg.to_dict())
                self.audit.write("publisher", "went_public", event=pkg.event_id)
                n += 1
        return n

    # ---- outputs --------------------------------------------------------------------------
    def _export(self, ev: Event, pkg: YouTubePackage) -> None:
        d = self.cfg.out_dir / ev.id
        d.mkdir(parents=True, exist_ok=True)
        (d / "package.json").write_text(json.dumps(pkg.to_dict(), indent=2, ensure_ascii=False))
        (d / "social.json").write_text(json.dumps(
            [{**p.__dict__, "when": p.when.isoformat()} for p in pkg.social_posts], indent=2, ensure_ascii=False))
        (d / "link_package.md").write_text(render_link_package(ev, pkg, self.cfg))

    def write_index_and_status(self) -> None:
        pk = [_pkg_from_dict(d) for d in self.store.packages()]
        evs = {e["id"]: Event.from_dict(e) for e in self.store.events()}
        rows = sorted(pk, key=lambda p: p.scheduled_start)
        md = ["# YouTube Link Packages", "", "| Date | Event | Status | Watch link | Package |", "|---|---|---|---|---|"]
        for p in rows:
            md.append(f"| {p.scheduled_start:%Y-%m-%d %H:%M} | {evs[p.event_id].title if p.event_id in evs else p.title} "
                      f"| {p.status.value} | {p.links.get('watch', '')} | [{p.event_id}]({p.event_id}/link_package.md) |")
        (self.cfg.out_dir / "index.md").write_text("\n".join(md) + "\n")
        upcoming = [p for p in rows if p.scheduled_start > self.now()]
        status = {
            "updated": self.now().isoformat(),
            "kill_switch": security.kill_switch_on(self.cfg),
            "publish_mode": self.cfg.publish_mode,
            "audit_chain_ok": self.audit.verify() if self.audit.path.exists() else True,
            "packages": {s.value: sum(p.status == s for p in pk) for s in PackageStatus},
            "next_event": upcoming[0].title if upcoming else None,
            "next_event_at": upcoming[0].scheduled_start.isoformat() if upcoming else None,
            "agents": {a: {"tasks": int(self.store.get(f"agent:{a}:tasks", "0") or 0),
                           "last_run": self.store.get(f"agent:{a}:last_run")} for a in AGENTS},
        }
        tmp = self.cfg.state_dir / "status.json.tmp"
        tmp.write_text(json.dumps(status, indent=2))
        tmp.replace(self.cfg.state_dir / "status.json")     # atomic for dashboard readers

    # ---- loop -----------------------------------------------------------------------------
    def run_once(self) -> dict[str, int]:
        r = {"new_events": len(self.ingest_new()), "built": self.process_events(),
             "published": self.publish_due(), "went_public": self.flip_visibility()}
        self.write_index_and_status()
        return r

    def run_forever(self) -> None:
        backoff = 1
        while True:
            try:
                log.info("tick: %s", self.run_once())
                backoff = 1
                time.sleep(self.cfg.poll_seconds)
            except KeyboardInterrupt:
                return
            except Exception:
                log.error("tick failed\n%s", traceback.format_exc())
                time.sleep(min(backoff * 30, 900))
                backoff *= 2


def _td(hours: int):
    from datetime import timedelta
    return timedelta(hours=hours)


def _pkg_from_dict(d: dict) -> YouTubePackage:
    from .models import SocialPost
    d = dict(d)
    d["visibility"] = Visibility(d["visibility"])
    d["status"] = PackageStatus(d["status"])
    d["scheduled_start"] = datetime.fromisoformat(d["scheduled_start"])
    d["social_posts"] = [SocialPost(**{**p, "when": datetime.fromisoformat(p["when"])}) for p in d["social_posts"]]
    return YouTubePackage(**d)


def render_link_package(ev: Event, pkg: YouTubePackage, cfg: Config) -> str:
    L = pkg.links
    posts = "\n".join(f"- **{p.platform}** · {p.purpose} · {p.when.astimezone(cfg.tz):%a %b %-d %H:%M %Z}\n\n  > " + p.text.replace("\n", "\n  > ")
                      for p in pkg.social_posts)
    findings = "\n".join(f"- `{f['severity']}` {f['code']}: {f['detail']}" for f in pkg.security_findings) or "- none"
    return f"""# {pkg.title}

**Status:** {pkg.status.value} · **Visibility:** {pkg.visibility.value} · **Start:** {ev.start.astimezone(cfg.tz):%A %b %-d, %Y %-I:%M %p %Z}

## Links
| | |
|---|---|
| Watch | {L.get('watch')} |
| Share | {L.get('share', 'pending')} |
| Studio edit | {L.get('studio_edit')} |
| Live control room | {L.get('live_control_room')} |
| Channel | {L.get('channel')} |

## Metadata
- **Playlists:** {', '.join(pkg.playlists)}
- **Category ID:** {pkg.category_id}
- **Tags:** {', '.join(pkg.tags)}
- **Thumbnail:** `{pkg.thumbnail_path}`
- **Post-stream VOD title:** {pkg.vod_title}

### Description
```
{pkg.description}
```

## Social drafts
{posts}

## Security findings
{findings}

## Notes
{chr(10).join('- ' + n for n in pkg.notes)}
"""
