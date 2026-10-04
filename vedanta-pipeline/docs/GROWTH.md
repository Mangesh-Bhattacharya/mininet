# Growth & monetisation playbook (what the agents optimise for)

| Lever | Mechanism in this repo | Human action still required |
|---|---|---|
| Discoverability | SEO agent: curated devotional bank + cached YouTube autocomplete; keyword-first titles ≤100 chars | Review top-performing titles monthly |
| Consistency | Scheduler: fixed weekly cadence, 24h go-public ramp so reminders work | Keep the stream key / encoder running |
| Click-through | Thumbnail agent: high-contrast typographic 1280×720, one idea per image | A/B test via Studio "Test & compare" |
| Retention | Chapter template, VOD entry with chapters | Add real timestamps after each stream |
| Reach | Social agent drafts (X, Threads, FB, IG, WhatsApp) at learned/default slots | Approve webhook automation |
| Shorts funnel | Package notes prompt 3 clips per stream | Cut clips (this is the main path to 1M views/mo) |
| Income | Donation + merch blocks in every description; YPP applications | Apply to YPP / merch shelf in Studio |

## Reality check on the targets
- Programme thresholds change; verify current YouTube Partner Programme requirements in Studio → Earn
  (historically 500 subs for fan-funding tier; 1,000 subs + 4,000 public watch hours or 10M Shorts views for ads).
- 1M views/month is ~80× the 12.4k shown on the dashboard. Long livestreams alone will not get there;
  expect it to come from Shorts clips of lectures plus search-driven evergreen content.
- Optimal posting times: YouTube exposes no hour-of-day API. The pipeline learns from your own video history
  (`learn_best_slots`) once ≥3 uploads share a slot; Studio → Analytics → "When your viewers are on YouTube"
  is the ground truth to put in `DEFAULT_SLOTS` (agents/scheduler.py).
