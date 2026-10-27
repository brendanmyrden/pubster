# Pubster

Private Swift engineering library. **Local/GitHub release; no public site deployed.**

## Working now

- 100 original atlas candidates + 13 separately recorded supplements.
- 2 rights-approved, commit-pinned Apple sources; 262 extracted documentation chunks.
- Canonical SQLite WAL/FTS5, line-span provenance, preserved licenses/notices.
- Deterministic JSONL/gzip/Markdown exports, SHA-256 manifests, local backup.
- Real Next.js static-export UI with Tailwind and shadcn/ui Button; no corpus in bundles.
- Authenticated Worker implementation: scrypt, hashed opaque sessions, CSRF, rate limits,
  protected search/reader/download API. Node integration tests are not remote Worker proof.
- Quiet hourly deterministic maintenance; approved sources rechecked after 24 hours,
  not refetched every hour. No-change runs do not rebuild the site or make empty commits.
- Bounded, model-free retrieval experiments with a frozen 20-query regression suite
  and separate development cases. Reject no improvement or any regression.

## Run locally

Installed on `/Volumes/SYYR/Pubster`; private state `/Volumes/SYYR/Pubster-state`.
The workspace's `pubster` path links here. Keep SYYR attached.

```sh
./scripts/pubsterctl status --json
./scripts/pubsterctl search 'adjacentPairs'
./scripts/pubsterctl validate --candidate
./scripts/pubsterctl export --candidate
./scripts/pubsterctl evaluate --suite launch
./scripts/pubsterctl run --once --no-notify
./scripts/pubsterctl pause
./scripts/pubsterctl resume
./scripts/pubsterctl scheduler inspect
```

The pinned pnpm launcher is installed under the external state's `tooling/node_modules/.bin`.
Use Python `requirements.lock` and `pnpm-lock.yaml` for reproducibility. Do not upgrade global tools.

## Honest boundaries

Cloudflare deployment deferred by user. No R2/D1 resources, public URL, or remote auth
acceptance proof. Inference and semantic retrieval are not configured; no paid model
calls occur. No Swift examples were executed. Only the two approved sources are
refreshed automatically; catalog candidates are not automatically rights-approved.
No reviewed skill packs, DocC JSON/HTML adapters, or cloud publication/rollback yet.
The local CLI is the operational interface; not every command in the aspirational
implementation specification is implemented. See `docs/OPERATIONS.md` and reports.

Generated research is not unrestricted self-modifying code or model training.
