"""Scheduler agent: broadcast time, visibility ramp, and social cadence.

Social slots: learned from channel history when available, else conservative defaults
for a Toronto-based community audience (evening, weekday lunch, Sunday morning).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..config import Config
from ..models import Event, SocialPost, Visibility

DEFAULT_SLOTS = [(12, 15), (19, 30)]   # local (hour, minute): lunch, evening


def _slot_on(day: datetime, cfg: Config, slots: list[tuple[int, int]], prefer: int = 1) -> datetime:
    h, m = slots[min(prefer, len(slots) - 1)]
    return day.astimezone(cfg.tz).replace(hour=h, minute=m, second=0, microsecond=0)


def social_schedule(event: Event, cfg: Config, now: datetime,
                    learned: list[tuple[int, int, float]] | None = None) -> list[tuple[str, datetime]]:
    slots = [(h, 0) for _, h, _ in learned] if learned else DEFAULT_SLOTS
    plan = [
        ("teaser", _slot_on(event.start - timedelta(days=7), cfg, slots)),
        ("reminder", _slot_on(event.start - timedelta(days=2), cfg, slots)),
        ("reminder", _slot_on(event.start - timedelta(days=1), cfg, slots)),
        ("live", event.start - timedelta(minutes=30)),
        ("recap", (event.end or event.start + timedelta(minutes=cfg.default_duration_minutes)) + timedelta(hours=3)),
    ]
    return [(p, t) for p, t in plan if t > now]       # never schedule into the past


def visibility_for(event: Event, cfg: Config, now: datetime) -> Visibility:
    """Configured default (private) until the go-public window opens; the publisher flips it."""
    return Visibility.PUBLIC if now >= go_public_at(event, cfg) else Visibility(cfg.default_visibility)


def go_public_at(event: Event, cfg: Config) -> datetime:
    return event.start - timedelta(hours=cfg.go_public_hours_before)


def rate_limit_ok(scheduled_today: int, cfg: Config) -> bool:
    return scheduled_today < cfg.daily_publish_cap


__all__ = ["social_schedule", "visibility_for", "go_public_at", "rate_limit_ok", "SocialPost"]
