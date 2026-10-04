"""Dispatch social drafts to a single configured HTTPS webhook (e.g. Zapier/Make) that owns
platform credentials, so no social tokens ever live in this process."""
from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

from ..config import Config
from ..models import SocialPost


def dispatch(cfg: Config, event_id: str, posts: list[SocialPost], dry_run: bool = True) -> int:
    if dry_run or not cfg.social_webhook_url:
        return 0
    if urlparse(cfg.social_webhook_url).scheme != "https":
        raise ValueError("social webhook must be https")
    sent = 0
    for p in posts:
        body = json.dumps({"event_id": event_id, "platform": p.platform, "text": p.text,
                           "publish_at": p.when.isoformat(), "purpose": p.purpose}).encode()
        req = urllib.request.Request(cfg.social_webhook_url, data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (https enforced above)
            sent += 200 <= r.status < 300
    return sent
