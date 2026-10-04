"""Calendar Extractor: newsletter text -> list[Event].

Deterministic parser first (no network, reproducible); optional LLM pass fills gaps. Events
below the confidence floor are dropped, never guessed.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta

from ..config import Config
from ..models import Event, EventKind

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(
    r"(?:(?:mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)[a-z]*,?\s+)?"
    r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>20\d{2}))?", re.I)
TIME_RE = re.compile(
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>a\.?m\.?|p\.?m\.?)"
    r"(?:\s*(?:-|–|to)\s*(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<ap2>a\.?m\.?|p\.?m\.?))?", re.I)
SPEAKER_RE = re.compile(r"\b(?:by|with|speaker:?)\s+((?:Swami|Pravrajika|Dr\.?|Prof\.?|Mr\.?|Ms\.?|Mrs\.?)\s+[A-Z][\w.\-]*(?:\s+[A-Z][\w.\-]*){0,3})")
KIND_KEYWORDS: list[tuple[EventKind, tuple[str, ...]]] = [
    (EventKind.FESTIVAL, ("jayanti", "janmotsav", "diwali", "durga", "kali puja", "christmas eve", "shivaratri", "birthday", "festival", "tithi")),
    (EventKind.BHAJAN, ("bhajan", "kirtan", "devotional music", "satsang")),
    (EventKind.PUJA, ("puja", "arati", "arotrik", "homa", "vesper")),
    (EventKind.MEDITATION, ("meditation", "japa")),
    (EventKind.RETREAT, ("retreat", "workshop", "seminar")),
    (EventKind.CLASS, ("class", "study circle", "gita", "upanishad", "gospel", "scripture")),
    (EventKind.LECTURE, ("lecture", "discourse", "talk", "sermon", "address")),
]
MIN_CONFIDENCE = 0.55


def _to_24h(h: int, m: int, ap: str) -> tuple[int, int]:
    ap = ap.lower().replace(".", "")
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return h, m


def classify(text: str) -> EventKind:
    low = text.lower()
    for kind, kws in KIND_KEYWORDS:
        if any(k in low for k in kws):
            return kind
    return EventKind.OTHER


def _resolve_year(mon: int, day: int, explicit: int | None, ref: date) -> int:
    if explicit:
        return explicit
    # newsletters are forward-looking; a date >6 months in the past means next year
    cand = date(ref.year, mon, min(day, 28))
    return ref.year + 1 if (ref - cand).days > 180 else ref.year


def _clean_title(title: str, speaker: str | None) -> str:
    title = re.split(r"(?<=[a-z\)\"])\.\s+[A-Z]", title)[0]          # first sentence only
    if speaker:
        title = re.sub(rf"\s*\b(?:by|with|speaker:?)\s+{re.escape(speaker)}\.?", "", title)
    title = re.sub(r"^(?:at|on|from)\s+", "", title.strip(" -–—:|,"), flags=re.I)
    title = re.sub(r"^(?:Lecture|Talk|Discourse) on\s+", "", title, flags=re.I)
    return title.strip(" -–—:|,\"'“”").rstrip(".")


def parse_events(text: str, cfg: Config, ref: date | None = None,
                 default_year: int | None = None) -> list[Event]:
    ref = ref or datetime.now(cfg.tz).date()
    lines = [ln.strip(" •*-\t") for ln in text.splitlines() if ln.strip()]
    events: list[Event] = []
    for i, line in enumerate(lines):
        dm = DATE_RE.search(line)
        if not dm:
            continue
        # context = this line + following lines until the next dated line (max 3)
        ctx = [line]
        for nxt in lines[i + 1:i + 4]:
            if DATE_RE.search(nxt):
                break
            ctx.append(nxt)
        blob = " ".join(ctx)
        tm = TIME_RE.search(blob)
        mon, day = MONTHS[dm["mon"][:3].lower()], int(dm["day"])
        year = _resolve_year(mon, day, int(dm["year"]) if dm["year"] else default_year, ref)
        try:
            d = date(year, mon, day)
        except ValueError:
            continue
        conf = 0.4 + (0.25 if tm else 0) + (0.2 if classify(blob) != EventKind.OTHER else 0)
        if tm:
            h, m = _to_24h(int(tm["h"]), int(tm["m"] or 0), tm["ap"])
        else:
            h, m = 11, 0  # documented default: Sunday service time; confidence stays low
        start = datetime(d.year, d.month, d.day, h, m, tzinfo=cfg.tz)
        end = None
        if tm and tm["h2"]:
            h2, m2 = _to_24h(int(tm["h2"]), int(tm["m2"] or 0), tm["ap2"])
            end = start.replace(hour=h2, minute=m2)
            if end <= start:
                end += timedelta(days=1)
        # title: remove the date/time fragments from the first line
        title = TIME_RE.sub("", DATE_RE.sub("", line))
        title = re.sub(r"^[\s:–—\-|,@]+|[\s:–—\-|,@]+$", "", title)
        if len(title) < 4 and len(ctx) > 1:
            title = re.sub(r"^[\s:–—\-|,@]+|[\s:–—\-|,@]+$", "", TIME_RE.sub("", ctx[1]))
        if len(title) < 4:
            continue
        sp = SPEAKER_RE.search(blob)
        title = _clean_title(title, sp.group(1) if sp else None)
        if len(title) < 4:
            continue
        kind = classify(blob)
        eid = hashlib.sha1(f"{start.isoformat()}|{title.lower()}".encode()).hexdigest()[:10]
        events.append(Event(
            id=f"{start:%Y%m%d}-{eid}", title=title[:140], kind=kind, start=start, end=end,
            speaker=sp.group(1) if sp else None,
            description=" ".join(ctx[1:])[:600], source_line=line[:300],
            confidence=round(min(conf + (0.1 if sp else 0), 1.0), 2)))
    # de-duplicate same start+title
    uniq = {e.id: e for e in events if e.confidence >= MIN_CONFIDENCE}
    return sorted(uniq.values(), key=lambda e: e.start)


def extract(text: str, cfg: Config, ref: date | None = None) -> list[Event]:
    events = parse_events(text, cfg, ref)
    if cfg.use_llm:
        from .. import llm
        if llm.available():
            events = _llm_merge(text, cfg, events, ref)
    return events


def _llm_merge(text: str, cfg: Config, base: list[Event], ref: date | None) -> list[Event]:
    from .. import llm
    try:
        rows = llm.complete_json(
            cfg.llm_model,
            "Extract events from a Vedanta temple newsletter. Return JSON list of objects "
            "{date:'YYYY-MM-DD', time:'HH:MM' or null, title, speaker|null, kind, description}. "
            "Never invent events, speakers or times.",
            text[:24000])
    except Exception:  # LLM is an enhancer only
        return base
    known = {(e.start.date(), e.title.lower()[:20]) for e in base}
    out = list(base)
    for r in rows if isinstance(rows, list) else []:
        try:
            d = date.fromisoformat(r["date"])
            hh, mm = map(int, (r.get("time") or "11:00").split(":"))
            start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=cfg.tz)
            title = str(r["title"])[:140]
            if (d, title.lower()[:20]) in known:
                continue
            eid = hashlib.sha1(f"{start.isoformat()}|{title.lower()}".encode()).hexdigest()[:10]
            out.append(Event(id=f"{start:%Y%m%d}-{eid}", title=title,
                             kind=EventKind(r.get("kind", "other")) if r.get("kind") in EventKind._value2member_map_ else classify(title),
                             start=start, speaker=r.get("speaker"), description=str(r.get("description", ""))[:600],
                             source_line="llm", confidence=0.6))
        except (KeyError, ValueError):
            continue
    return sorted(out, key=lambda e: e.start)
