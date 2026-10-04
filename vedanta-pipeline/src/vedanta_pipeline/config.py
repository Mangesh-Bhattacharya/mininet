from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Config:
    # identity
    org_name: str = "Vedanta Society of Toronto"
    channel_handle: str = "@VedantaToronto"
    channel_url: str = "https://www.youtube.com/@VedantaToronto"
    website: str = "https://vedantatoronto.ca"
    timezone: str = "America/Toronto"
    # paths
    inbox_dir: Path = Path("inbox")
    out_dir: Path = Path("out")
    state_dir: Path = Path("state")
    # monetisation links (empty = omitted from output)
    donation_url: str = ""
    merch_url: str = ""
    charity_receipt_text: str = ""   # only emitted if explicitly provided
    # behaviour
    publish_mode: str = "draft"      # draft | schedule  (schedule = auto-create broadcasts after gate)
    default_visibility: str = "private"
    go_public_hours_before: int = 24
    category_id: str = "27"          # Education
    default_duration_minutes: int = 90
    poll_seconds: int = 900
    # LLM (optional)
    llm_model: str = "claude-sonnet-5-5"
    use_llm: bool = False
    # security
    allowed_domains: tuple[str, ...] = (
        "vedantatoronto.ca", "youtube.com", "youtu.be", "studio.youtube.com",
    )
    allowed_contacts: tuple[str, ...] = ()   # emails/phones permitted in public text
    social_webhook_url: str = ""             # e.g. Zapier catch hook (https only)
    daily_publish_cap: int = 6               # default YouTube quota supports ~6 uploads/day
    kill_switch_file: Path = Path("state/KILL")
    playlists: dict[str, str] = field(default_factory=lambda: {
        "lecture": "Sunday Lectures",
        "class": "Scripture Classes",
        "bhajan": "Devotional Music & Bhajans",
        "puja": "Festivals & Pujas",
        "festival": "Festivals & Pujas",
        "meditation": "Guided Meditation",
        "retreat": "Retreats & Special Programs",
        "other": "Vedanta Society of Toronto",
    })

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def all_allowed_domains(self) -> tuple[str, ...]:
        extra = tuple(
            d.split("//")[-1].split("/")[0].removeprefix("www.")
            for d in (self.donation_url, self.merch_url, self.website) if d
        )
        return tuple(dict.fromkeys(self.allowed_domains + extra))


def load_config(path: str | Path | None = None) -> Config:
    """Load a sectioned TOML file; section names are cosmetic, keys are flattened.
    A [playlists] table maps event kind -> playlist name."""
    if path is None or not Path(path).exists():
        return Config()
    raw = tomllib.loads(Path(path).read_text())
    flat: dict = {}
    for k, v in raw.items():
        if isinstance(v, dict) and k != "playlists":
            flat.update(v)
        else:
            flat[k] = v
    known = Config.__dataclass_fields__
    unknown = set(flat) - set(known)
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    for k, v in list(flat.items()):
        if k.endswith("_dir") or k == "kill_switch_file":
            flat[k] = Path(v)
        elif k in ("allowed_domains", "allowed_contacts"):
            flat[k] = tuple(v)
    return Config(**flat)
