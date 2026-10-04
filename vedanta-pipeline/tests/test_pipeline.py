from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from vedanta_pipeline.agents import extract, packager, security, seo
from vedanta_pipeline.config import Config
from vedanta_pipeline.models import EventKind, PackageStatus
from vedanta_pipeline.orchestrator import Pipeline

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_newsletter.txt"
TZ = ZoneInfo("America/Toronto")
NOW = datetime(2026, 10, 2, 16, 0, tzinfo=TZ)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(inbox_dir=tmp_path / "inbox", out_dir=tmp_path / "out", state_dir=tmp_path / "state",
                  donation_url="https://vedantatoronto.ca/donate", merch_url="https://vedantatoronto.ca/store",
                  kill_switch_file=tmp_path / "state" / "KILL")


def test_extracts_calendar(cfg):
    evs = extract.parse_events(SAMPLE.read_text(), cfg, NOW.date())
    assert len(evs) == 6
    first = evs[0]
    assert first.start == datetime(2026, 10, 4, 11, 0, tzinfo=TZ)
    assert first.kind == EventKind.LECTURE and first.speaker == "Swami Sarvapriyananda"
    assert evs[1].end == datetime(2026, 10, 11, 12, 30, tzinfo=TZ)
    assert {e.kind for e in evs} >= {EventKind.CLASS, EventKind.BHAJAN, EventKind.FESTIVAL, EventKind.MEDITATION}


def test_package_limits_and_no_angle_brackets(cfg):
    ev = extract.parse_events(SAMPLE.read_text(), cfg, NOW.date())[0]
    pkg = packager.build_package(ev, cfg, seo.research_keywords(ev), NOW)
    assert len(pkg.title) <= 100 and len(pkg.description.encode()) <= 5000
    assert sum(len(t) + 1 for t in pkg.tags) <= 500 and "<" not in pkg.description
    assert "donate" in pkg.description and "store" in pkg.description


def test_security_blocks_pii_secrets_and_foreign_urls(cfg):
    ev = extract.parse_events(SAMPLE.read_text(), cfg, NOW.date())[0]
    pkg = packager.build_package(ev, cfg, [], NOW)
    pkg.description += "\ncall 416-555-0199 or mail a@b.com see http://evil.example/x key AIza" + "A" * 35
    codes = {f.code for f in security.review_package(pkg, cfg)}
    assert {"pii_phone", "pii_email", "url_scheme", "secret"} <= codes


def test_audit_chain_detects_tampering(tmp_path):
    log = security.AuditLog(tmp_path / "a.jsonl")
    for i in range(3):
        log.write("t", "x", i=i)
    assert log.verify()
    lines = (tmp_path / "a.jsonl").read_text().splitlines()
    lines[1] = lines[1].replace('"i": 1', '"i": 9')
    (tmp_path / "a.jsonl").write_text("\n".join(lines) + "\n")
    assert not log.verify()


def test_credential_checks(tmp_path):
    t = tmp_path / "token.json"
    t.write_text("{}"); t.chmod(0o644)
    codes = {f.code for f in security.check_credentials(t, ["https://mail.google.com/"])}
    assert codes == {"token_perms", "scope_forbidden"}


def test_end_to_end_idempotent_and_kill_switch(cfg):
    cfg.inbox_dir.mkdir(parents=True)
    shutil.copy(SAMPLE, cfg.inbox_dir / "oct.txt")
    p = Pipeline(cfg, clock=lambda: NOW)
    r1 = p.run_once()
    assert r1["new_events"] == 6 and r1["built"] == 6
    pk = p.store.packages()
    # the Nov 7 event contains an unlisted phone/email in its description -> must be blocked
    statuses = {x["event_id"]: x["status"] for x in pk}
    assert list(statuses.values()).count(PackageStatus.BLOCKED.value) == 1
    assert list(statuses.values()).count(PackageStatus.READY.value) == 5
    assert (cfg.out_dir / "index.md").exists() and (cfg.state_dir / "status.json").exists()
    assert all(Path(x["thumbnail_path"]).stat().st_size < 2_000_000 for x in pk)
    r2 = p.run_once()                                   # nothing new -> nothing rebuilt
    assert r2["new_events"] == 0 and r2["built"] == 0
    assert p.audit.verify()


def test_kill_switch_blocks_everything(cfg):
    cfg.inbox_dir.mkdir(parents=True)
    shutil.copy(SAMPLE, cfg.inbox_dir / "oct.txt")
    cfg.kill_switch_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.kill_switch_file.touch()
    p = Pipeline(cfg, clock=lambda: NOW)
    p.run_once()
    assert {x["status"] for x in p.store.packages()} == {"blocked"}


def test_titles_are_clean(cfg):
    titles = [e.title for e in extract.parse_events(SAMPLE.read_text(), cfg, NOW.date())]
    assert titles[0] == "Swami Vivekananda's Karma Yoga"
    assert "Durga Puja Sandhi Puja and Arati" in titles
    assert not any("@" in t or "416" in t for t in titles)
