"""Social Media agent: platform-aware drafts. Pure text generation; dispatch is separate and
passes through the Security agent."""
from __future__ import annotations

from datetime import datetime

from ..config import Config
from ..models import Event, SocialPost, YouTubePackage
from . import scheduler

LIMITS = {"x": 280, "threads": 500, "facebook": 63000, "instagram": 2200, "whatsapp": 1000}
PURPOSE_LINES = {
    "teaser": "🙏 Coming up at the Vedanta Society of Toronto",
    "reminder": "🔔 Reminder",
    "live": "🔴 We go live soon",
    "recap": "✨ Missed it? Watch the recording",
}


def _fit(text: str, limit: int, keep_tail: str) -> str:
    if len(text) <= limit:
        return text
    head = limit - len(keep_tail) - 2
    return text[:head].rstrip() + "…\n" + keep_tail


def draft(event: Event, pkg: YouTubePackage, cfg: Config, now: datetime,
          learned: list[tuple[int, int, float]] | None = None, link: str | None = None) -> list[SocialPost]:
    link = link or cfg.channel_url
    when = event.start.astimezone(cfg.tz).strftime("%a %b %-d, %-I:%M %p %Z")
    tags = "#Vedanta #SriRamakrishna #Toronto"
    posts: list[SocialPost] = []
    for purpose, t in scheduler.social_schedule(event, cfg, now, learned):
        lead = PURPOSE_LINES[purpose]
        who = f" with {event.speaker}" if event.speaker else ""
        body = f"{lead}: {event.title}{who}\n📅 {when}\n"
        for platform, limit in LIMITS.items():
            tail = f"{link}" if platform != "instagram" else "Link in bio"
            text = _fit(body + (tail if platform != "x" else f"{tail} {tags.split()[0]}"), limit, tail)
            if platform in ("instagram", "facebook", "threads"):
                text = _fit(text + f"\n{tags}", limit, tags)
            posts.append(SocialPost(platform, text, t, purpose, pkg.thumbnail_path))
    return posts
