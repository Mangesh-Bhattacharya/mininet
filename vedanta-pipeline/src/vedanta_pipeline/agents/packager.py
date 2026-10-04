"""YouTube Packager: title, description, tags, playlists, chapters, VOD entry, link package."""
from __future__ import annotations

import re
from datetime import datetime

from ..config import Config
from ..models import Event, EventKind, YouTubePackage
from . import merch, scheduler

TITLE_MAX, DESC_MAX_BYTES, TAGS_MAX_CHARS = 100, 5000, 500
KIND_LABEL = {
    EventKind.LECTURE: "Live Lecture", EventKind.CLASS: "Live Class", EventKind.BHAJAN: "Live Bhajans",
    EventKind.PUJA: "Live Puja", EventKind.FESTIVAL: "Live Celebration",
    EventKind.MEDITATION: "Guided Meditation", EventKind.RETREAT: "Retreat", EventKind.OTHER: "Live",
}
CHAPTER_TEMPLATE = {
    EventKind.LECTURE: ["Opening prayer / meditation", "Introduction", "Lecture", "Q&A", "Closing"],
    EventKind.CLASS: ["Opening prayer", "Recap", "Class", "Discussion", "Closing"],
    EventKind.BHAJAN: ["Opening", "Bhajans", "Closing prayer"],
    EventKind.PUJA: ["Opening", "Puja", "Arati", "Prasad announcement"],
    EventKind.FESTIVAL: ["Opening", "Program", "Arati", "Closing"],
    EventKind.MEDITATION: ["Settling in", "Meditation", "Closing"],
}


def _sanitize(s: str) -> str:
    return re.sub(r"[<>]", "", s).strip()   # YouTube rejects angle brackets


def build_title(event: Event, primary: str, now_year: int) -> str:
    label = KIND_LABEL[event.kind]
    base = event.title
    # avoid "Lecture - Live Lecture" duplication
    suffix = "" if label.split()[-1].lower() in base.lower() else f" | {label}"
    who = f" with {event.speaker}" if event.speaker and event.speaker not in base else ""
    tail = " | Vedanta Society of Toronto"
    t = _sanitize(f"{base}{who}{suffix}")
    return (t + tail if len(t + tail) <= TITLE_MAX else t)[:TITLE_MAX].rstrip(" |")


def build_tags(event: Event, keywords: list[str]) -> list[str]:
    tags: list[str] = []
    total = 0
    cand = keywords + ["vedanta", "hinduism", "toronto", "livestream", "ramakrishna order"]
    if event.speaker:
        cand.insert(2, event.speaker.lower())
    for t in cand:
        t = _sanitize(t.lower())
        if t and t not in tags and total + len(t) + 1 <= TAGS_MAX_CHARS - 20 and len(tags) < 15:
            tags.append(t)
            total += len(t) + 1
    return tags


def build_description(event: Event, cfg: Config, keywords: list[str], hashtags: list[str]) -> str:
    when = event.start.astimezone(cfg.tz).strftime("%A, %B %-d, %Y at %-I:%M %p %Z")
    hook = f"Join the {cfg.org_name} for {KIND_LABEL[event.kind].lower()}: {event.title}."
    if event.speaker:
        hook += f" Speaker: {event.speaker}."
    parts = [hook, f"📅 {when}", "",
             event.description.strip() if event.description else "",
             f"Subscribe for weekly lectures, classes and devotional programs: {cfg.channel_url}?sub_confirmation=1",
             ""]
    chapters = CHAPTER_TEMPLATE.get(event.kind)
    if chapters:
        parts += ["Chapters (timestamps are added after the stream):"] + [f"• {c}" for c in chapters] + [""]
    for blk in (merch.donation_block(cfg), merch.merch_block(cfg)):
        if blk:
            parts += [blk, ""]
    parts += [f"🌐 {cfg.website}", "", "About: Vedanta teaches the unity of existence and the divinity of the soul, "
              "as lived and taught by Sri Ramakrishna, Holy Mother Sri Sarada Devi and Swami Vivekananda.", "",
              " ".join(hashtags[:3])]
    text = _sanitize("\n".join(p for p in parts))
    text = re.sub(r"\n{3,}", "\n\n", text)
    while len(text.encode()) > DESC_MAX_BYTES:
        text = text[: int(len(text) * 0.9)].rsplit("\n", 1)[0]
    return text


def build_package(event: Event, cfg: Config, keywords: list[str], now: datetime) -> YouTubePackage:
    primary = keywords[0] if keywords else "vedanta"
    hashtags = ["#Vedanta", f"#{re.sub(r'[^A-Za-z]', '', cfg.channel_handle)}", "#SriRamakrishna", "#SwamiVivekananda"]
    pkg = YouTubePackage(
        event_id=event.id,
        title=build_title(event, primary, now.year),
        description=build_description(event, cfg, keywords, hashtags),
        tags=build_tags(event, keywords),
        visibility=scheduler.visibility_for(event, cfg, now),
        category_id=cfg.category_id,
        scheduled_start=event.start,
        playlists=[cfg.playlists.get(event.kind.value, cfg.playlists["other"])],
        keywords_primary=keywords[:5],
    )
    pkg.vod_title = _sanitize(f"{event.title} | {event.start:%b %-d, %Y} | Vedanta Society of Toronto")[:TITLE_MAX]
    pkg.vod_description = pkg.description.replace("Chapters (timestamps are added after the stream):",
                                                  "Chapters:")
    pkg.links = {
        "channel": cfg.channel_url,
        "watch": "pending (created after broadcast is scheduled)",
        "studio_edit": "pending", "live_control_room": "pending", "embed": "pending",
    }
    pkg.notes = [f"go-public at {scheduler.go_public_at(event, cfg).isoformat()}",
                 "add chapter timestamps + cut 3 Shorts clips after the stream"]
    return pkg
