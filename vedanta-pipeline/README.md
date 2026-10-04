# Vedanta Pipeline

Newsletter → event calendar → YouTube livestream/VOD package + social drafts, run 24×7 by eight cooperating agents.

```
inbox/ ─► Newsletter Scanner ─► Calendar Extractor ─► [per event, parallel]
          SEO Optimizer · YouTube Packager · Thumbnail Designer · Social Media · Scheduler · Merch & Monetize
                                   │
                                   ▼
                        Security & Compliance GATE ──blocked──► out/<id>/ (findings listed)
                                   │ready
                    publish_mode=schedule? ─► YouTube Data API (broadcast, bind, thumbnail, playlist, tags)
                                   ▼
        out/index.md · out/<id>/link_package.md · state/status.json (dashboard feed) · state/audit.jsonl
```

## Quick start
```bash
cd vedanta-pipeline
pip install -e ".[google,pdf,dev]"
cp config.example.toml config.toml        # set donation_url, merch_url, allowed_contacts
cp ../your-newsletter.pdf inbox/          # manual import
vedanta once                              # builds packages in out/ (draft mode: nothing touches YouTube)
pytest
```

## Going autonomous
1. Google Cloud project → enable YouTube Data API v3 → OAuth client (Desktop) → `secrets/client_secret.json`.
2. `vedanta auth` once on a machine with a browser (token saved 0600; scope `youtube` only).
3. Set `publish_mode = "schedule"`, deploy with `deploy/vedanta-pipeline.service` or `deploy/Dockerfile`; run `vedanta run`.
4. Emergency stop: `touch state/KILL` (blocks gate + publishing). `vedanta verify-audit` checks the log hash chain.

## Safety model
- Defaults: draft mode, private visibility, no network writes. Autonomy is opt-in.
- Security gate blocks: secrets, unlisted emails/phones, non-https or non-allowlisted URLs, risky claims
  (e.g. "tax-deductible" unless you supply `charity_receipt_text`), YouTube limit violations, quota overrun.
- Gmail is not accessed: you import newsletters manually. Social credentials live in your webhook service, not here.
- Stream keys are never read or stored; the pipeline binds your existing reusable stream inside YouTube.

## Quota
~250 units/event (daily default 10,000). `daily_publish_cap` guards it.

See `docs/GROWTH.md` for the growth/monetisation plan and its caveats.
