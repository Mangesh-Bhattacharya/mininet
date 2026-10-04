"""SEO Optimizer: keyword research with a curated devotional bank + live YouTube autocomplete.

Autocomplete (suggestqueries.google.com) is an undocumented endpoint, so every call is cached,
rate-limited and failure-tolerant. Quota-costly Data API search.list is deliberately avoided.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime

from ..models import Event, EventKind
from ..store import Store

# Seed bank per kind; the order is priority. Phrasing follows the Ramakrishna Order's usage.
BANK: dict[EventKind, list[str]] = {
    EventKind.LECTURE: ["vedanta lecture", "swami vivekananda teachings", "advaita vedanta explained",
                        "sri ramakrishna teachings", "vedanta for beginners", "spiritual lecture live"],
    EventKind.CLASS: ["bhagavad gita class", "upanishad class", "gospel of sri ramakrishna",
                      "vedanta study", "gita chapter explained"],
    EventKind.BHAJAN: ["ramakrishna bhajan", "devotional songs", "kirtan live", "bhajan satsang"],
    EventKind.PUJA: ["puja live stream", "arati live", "hindu worship online", "temple live darshan"],
    EventKind.FESTIVAL: ["hindu festival live", "temple celebration live", "jayanti celebration", "puja live stream"],
    EventKind.MEDITATION: ["guided meditation", "vedanta meditation", "japa meditation", "meditation for peace"],
    EventKind.RETREAT: ["spiritual retreat", "vedanta retreat", "meditation retreat toronto"],
    EventKind.OTHER: ["vedanta society", "hindu temple toronto"],
}
ALWAYS = ["vedanta society of toronto", "vedanta toronto", "ramakrishna vivekananda", "hindu temple toronto"]
FESTIVAL_HINTS = {
    "diwali": ["diwali puja live", "deepavali celebration", "kali puja"],
    "durga": ["durga puja live", "navaratri", "durga puja toronto"],
    "kali": ["kali puja live", "sri ramakrishna kali"],
    "christmas": ["christmas eve vedanta", "jesus christ vedanta"],
    "shivaratri": ["maha shivaratri live", "shiva puja"],
    "jayanti": ["jayanti celebration", "swami vivekananda birthday", "sri ramakrishna birthday"],
    "janmotsav": ["janmotsav celebration"],
}


class Autocomplete:
    URL = "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={q}"

    def __init__(self, store: Store, ttl_hours: int = 72, enabled: bool = True):
        self.store, self.ttl, self.enabled = store, ttl_hours * 3600, enabled
        self._last = 0.0

    def suggest(self, q: str) -> list[str]:
        key = f"ac:{q}"
        cached = self.store.get(key)
        if cached:
            ts, vals = json.loads(cached)
            if time.time() - ts < self.ttl:
                return vals
        if not self.enabled:
            return []
        time.sleep(max(0.0, 1.0 - (time.time() - self._last)))   # ≤1 req/s
        self._last = time.time()
        try:
            req = urllib.request.Request(self.URL.format(q=urllib.parse.quote(q)),
                                         headers={"User-Agent": "vedanta-pipeline/0.1"})
            with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 (fixed https host)
                vals = [str(s) for s in json.loads(r.read().decode("utf-8", "replace"))[1]][:10]
        except Exception:
            return []
        self.store.set(key, json.dumps([time.time(), vals]))
        return vals


def research_keywords(event: Event, ac: Autocomplete | None = None, limit: int = 12) -> list[str]:
    low = f"{event.title} {event.description}".lower()
    ranked: list[str] = []
    for hint, kws in FESTIVAL_HINTS.items():
        if hint in low:
            ranked += kws
    ranked += BANK.get(event.kind, []) + ALWAYS
    if ac:
        for seed in ranked[:3]:
            # keep only suggestions that extend the seed (relevance guard against drift)
            ranked += [s for s in ac.suggest(seed) if seed.split()[0] in s]
    seen: dict[str, None] = {}
    for k in ranked:
        seen.setdefault(k.strip().lower(), None)
    return list(seen)[:limit]


def learn_best_slots(videos: list[tuple[datetime, int]], top: int = 3) -> list[tuple[int, int, float]]:
    """From the channel's own history (published_at, views_in_first_28d) return the best
    (weekday, hour, mean_views) slots. Needs >=3 samples per slot to be considered."""
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for ts, views in videos:
        buckets[(ts.weekday(), ts.hour)].append(views)
    scored = [(d, h, sum(v) / len(v)) for (d, h), v in buckets.items() if len(v) >= 3]
    return sorted(scored, key=lambda t: -t[2])[:top]
