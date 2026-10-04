"""Thumbnail Designer: deterministic 1280x720 PNG (<2MB) with high-contrast text.

No generative imagery of deities/people: a typographic design with a saffron palette keeps
output respectful, brand-consistent and policy-safe. Optional logo/photo from assets dir.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import Config
from ..models import Event, EventKind

W, H = 1280, 720
PALETTE = {
    EventKind.LECTURE: ((24, 18, 52), (255, 153, 51)),
    EventKind.CLASS: ((18, 36, 52), (255, 183, 77)),
    EventKind.BHAJAN: ((52, 18, 36), (255, 138, 101)),
    EventKind.PUJA: ((60, 20, 12), (255, 179, 0)),
    EventKind.FESTIVAL: ((70, 14, 24), (255, 193, 7)),
    EventKind.MEDITATION: ((14, 40, 44), (128, 222, 234)),
    EventKind.RETREAT: ((20, 44, 30), (174, 213, 129)),
    EventKind.OTHER: ((24, 24, 40), (255, 153, 51)),
}
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf", "C:/Windows/Fonts/georgiab.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        row = tuple(int(top[i] * (1 - t) + bottom[i] * t * 0.35) for i in range(3))
        for x in range(W):
            px[x, y] = row
    return img


def render(event: Event, cfg: Config, out: Path, assets: Path | None = None) -> Path:
    bg, accent = PALETTE[event.kind]
    img = _gradient(bg, (0, 0, 0))
    d = ImageDraw.Draw(img)
    # sun-disc motif (abstract, non-figurative)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W - 520, -160, W + 120, 480), fill=tuple(int(c * 0.55) for c in accent))
    img = Image.blend(img, Image.composite(glow, img, glow.convert("L")), 0.6).filter(ImageFilter.GaussianBlur(2))
    d = ImageDraw.Draw(img)
    if assets and (assets / "logo.png").exists():
        logo = Image.open(assets / "logo.png").convert("RGBA")
        logo.thumbnail((140, 140))
        img.paste(logo, (48, 40), logo)

    d.rectangle((48, 200, 60, 560), fill=accent)
    kind_txt = {"lecture": "LIVE LECTURE", "class": "LIVE CLASS", "bhajan": "LIVE BHAJANS", "puja": "LIVE PUJA",
                "festival": "LIVE CELEBRATION", "meditation": "MEDITATION", "retreat": "RETREAT",
                "other": "LIVE"}[event.kind.value]
    d.text((84, 190), kind_txt, font=_font(40), fill=accent)
    title = event.title.upper() if len(event.title) < 28 else event.title
    lines = textwrap.wrap(title, width=18)[:3]
    size = 104 if len(lines) <= 2 else 84
    y = 250
    for ln in lines:
        d.text((84 + 3, y + 3), ln, font=_font(size), fill=(0, 0, 0))     # shadow for contrast
        d.text((84, y), ln, font=_font(size), fill=(255, 255, 255))
        y += size + 8
    when = event.start.astimezone(cfg.tz).strftime("%a %b %-d  •  %-I:%M %p %Z")
    d.text((84, H - 150), when, font=_font(46), fill=accent)
    if event.speaker:
        d.text((84, H - 90), event.speaker, font=_font(34), fill=(235, 235, 235))
    d.text((W - 48, H - 50), cfg.org_name, font=_font(26), fill=(210, 210, 210), anchor="rs")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    if out.stat().st_size > 2_000_000:   # YouTube limit; fall back to JPEG
        out = out.with_suffix(".jpg")
        img.save(out, "JPEG", quality=88)
    return out
