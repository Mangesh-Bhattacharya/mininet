"""Newsletter Scanner agent: turns a manually imported newsletter file into clean text.

Supported: .txt .md .html/.htm .eml .pdf (needs pypdf). Untrusted input: all markup is
stripped and no remote content is fetched.
"""
from __future__ import annotations

import email
import html
import re
from email import policy
from html.parser import HTMLParser
from pathlib import Path

SUPPORTED = {".txt", ".md", ".html", ".htm", ".eml", ".pdf"}
MAX_BYTES = 25 * 1024 * 1024


class _Text(HTMLParser):
    SKIP = {"script", "style", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(src: str) -> str:
    p = _Text()
    p.feed(src)
    return html.unescape("".join(p.out))


def _clean(text: str) -> str:
    text = text.replace(" ", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def read_newsletter(path: Path) -> str:
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"unsupported file type: {path.suffix}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("file too large")
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("install vedanta-pipeline[pdf] to read PDFs") from e
        return _clean("\n".join(pg.extract_text() or "" for pg in PdfReader(str(path)).pages))
    if ext == ".eml":
        msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
        body = msg.get_body(preferencelist=("plain", "html"))
        content = body.get_content() if body else ""
        return _clean(html_to_text(content) if body and body.get_content_type() == "text/html" else content)
    raw = path.read_text(errors="replace")
    return _clean(html_to_text(raw) if ext in {".html", ".htm"} else raw)


def pending_files(inbox: Path) -> list[Path]:
    inbox.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
