# Pubster implementation handover — 2026-10-27

Local/GitHub release. Cloudflare explicitly deferred by the user. No live site URL.

Implemented: 113 catalog entries, 2 approved sources, 262 source-verified excerpts,
SQLite WAL/FTS5, deterministic exports (271 listed artifacts), source licenses/notices,
Next static UI, authenticated Worker source and Node integration tests, bounded
hourly maintenance/Git sync and numeric retrieval research.

Verification: Next production build; web/edge TypeScript checks; 9 pipeline tests;
8 Worker logic/API tests; no-change export byte comparison; all 271 artifact hashes;
111 public build files scanned for corpus identifiers/verifier leakage. Remote edge
runtime, browser/mobile interaction and public deployment are not verified.

20-query regression suite: recall@10 1.0; MRR 0.975. Narrow launch suite, not expert
coverage. Two ranking experiments rejected (no gain / regression); no changes retained.
No model calls, inference or semantic search. No reviewed skill packs or executed
Swift examples. DocC JSON/HTML adapters and cloud publisher remain future work.

Private repository: https://github.com/brendanmyrden/pubster
Code: /Volumes/SYYR/Pubster
State: /Volumes/SYYR/Pubster-state
The existing supplied-password verifier remains outside Git on the internal disk.

Scheduler registration/manual-run evidence is recorded separately in scheduler.json.
A manual trigger does not prove an actual clock-triggered occurrence.

Scheduler enabled: `a8c25970-7b94-46fc-9203-19293294a222`, hourly at minute 0 Toronto, delivery none. Manual OpenClaw run succeeded; no clock-triggered occurrence yet observed. Approved export private release uploaded, downloaded and SHA-256 verified; see release.json.
