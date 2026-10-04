"""Thin optional LLM wrapper (Anthropic). Everything works without it; LLM output is always
re-validated by deterministic code and the Security agent."""
from __future__ import annotations

import json
import os
import re
from typing import Any


def available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete_json(model: str, system: str, prompt: str, max_tokens: int = 4000) -> Any:
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    if not m:
        raise ValueError("LLM returned no JSON")
    return json.loads(m.group(1))
