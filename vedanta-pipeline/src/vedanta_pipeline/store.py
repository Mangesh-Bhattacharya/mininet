from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS newsletters(
  sha256 TEXT PRIMARY KEY, path TEXT, ingested_at REAL, month TEXT);
CREATE TABLE IF NOT EXISTS events(
  id TEXT PRIMARY KEY, newsletter TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS packages(
  event_id TEXT PRIMARY KEY, status TEXT, data TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT, updated_at REAL);
"""


class Store:
    """SQLite state (idempotency, resumability). Single writer; WAL for dashboard readers."""

    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.path = state_dir / "pipeline.db"
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self.path.chmod(0o600)

    def _q(self, sql: str, args: tuple = ()):
        with self._lock:
            return self._db.execute(sql, args)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._db:
            yield self._db

    def seen_newsletter(self, sha: str) -> bool:
        return self._q("SELECT 1 FROM newsletters WHERE sha256=?", (sha,)).fetchone() is not None

    def add_newsletter(self, sha: str, path: str, month: str) -> None:
        with self.tx() as db:
            db.execute("INSERT OR IGNORE INTO newsletters VALUES(?,?,?,?)", (sha, path, time.time(), month))

    def put_event(self, event_id: str, newsletter: str, data: dict[str, Any]) -> None:
        with self.tx() as db:
            db.execute("INSERT OR REPLACE INTO events VALUES(?,?,?)", (event_id, newsletter, json.dumps(data)))

    def events(self) -> list[dict[str, Any]]:
        return [json.loads(r[0]) for r in self._q("SELECT data FROM events")]

    def put_package(self, event_id: str, status: str, data: dict[str, Any]) -> None:
        with self.tx() as db:
            db.execute("INSERT OR REPLACE INTO packages VALUES(?,?,?,?)",
                       (event_id, status, json.dumps(data), time.time()))

    def package(self, event_id: str) -> dict[str, Any] | None:
        r = self._q("SELECT data FROM packages WHERE event_id=?", (event_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def packages(self, status: str | None = None) -> list[dict[str, Any]]:
        q, a = "SELECT data FROM packages", ()
        if status:
            q, a = q + " WHERE status=?", (status,)
        return [json.loads(r[0]) for r in self._db.execute(q, a)]

    def get(self, k: str, default: str | None = None) -> str | None:
        r = self._q("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def set(self, k: str, v: str) -> None:
        with self.tx() as db:
            db.execute("INSERT OR REPLACE INTO kv VALUES(?,?,?)", (k, v, time.time()))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
