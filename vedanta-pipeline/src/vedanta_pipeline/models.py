from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    LECTURE = "lecture"
    CLASS = "class"
    BHAJAN = "bhajan"
    PUJA = "puja"
    FESTIVAL = "festival"
    MEDITATION = "meditation"
    RETREAT = "retreat"
    OTHER = "other"


class Visibility(str, Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class PackageStatus(str, Enum):
    DRAFT = "draft"
    BLOCKED = "blocked"          # failed security gate
    READY = "ready"              # passed gate, awaiting publish/approval
    SCHEDULED = "scheduled"      # broadcast created on YouTube
    PUBLISHED = "published"


@dataclass
class Event:
    id: str
    title: str
    kind: EventKind
    start: datetime               # timezone-aware
    end: datetime | None = None
    speaker: str | None = None
    location: str | None = None
    description: str = ""
    source_line: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat() if self.end else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        return cls(
            **{**d, "kind": EventKind(d["kind"]),
               "start": datetime.fromisoformat(d["start"]),
               "end": datetime.fromisoformat(d["end"]) if d.get("end") else None}
        )


@dataclass
class SocialPost:
    platform: str
    text: str
    when: datetime
    purpose: str                  # teaser | reminder | live | recap
    media: str | None = None


@dataclass
class YouTubePackage:
    event_id: str
    title: str
    description: str
    tags: list[str]
    visibility: Visibility
    category_id: str
    scheduled_start: datetime
    thumbnail_path: str | None = None
    playlists: list[str] = field(default_factory=list)
    keywords_primary: list[str] = field(default_factory=list)
    social_posts: list[SocialPost] = field(default_factory=list)
    vod_title: str = ""
    vod_description: str = ""
    links: dict[str, str] = field(default_factory=dict)
    status: PackageStatus = PackageStatus.DRAFT
    security_findings: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["visibility"] = self.visibility.value
        d["status"] = self.status.value
        d["scheduled_start"] = self.scheduled_start.isoformat()
        for p in d["social_posts"]:
            p["when"] = p["when"].isoformat()
        return d
