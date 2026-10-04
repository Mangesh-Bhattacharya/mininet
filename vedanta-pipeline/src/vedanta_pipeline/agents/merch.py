"""Merch & Monetize agent: donation and merchandise messaging.

Rules: never promise tax receipts unless configured, never imply merch is required for
spiritual benefit, never use pressure language.
"""
from __future__ import annotations

from ..config import Config


def donation_block(cfg: Config) -> str:
    lines = []
    if cfg.donation_url:
        lines.append(f"🙏 Support the Society's programs and upkeep: {cfg.donation_url}")
        lines.append("Every offering, large or small, helps us keep these teachings freely available.")
        if cfg.charity_receipt_text:
            lines.append(cfg.charity_receipt_text)
    return "\n".join(lines)


def merch_block(cfg: Config) -> str:
    if not cfg.merch_url:
        return ""
    return (f"🛍️ Temple store (cups, shirts, hoodies, stationery): {cfg.merch_url}\n"
            "Proceeds support the Vedanta Society of Toronto.")


def social_cta(cfg: Config) -> str:
    return "Support: " + cfg.donation_url if cfg.donation_url else ""
