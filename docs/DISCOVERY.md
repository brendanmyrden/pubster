# Public repository discovery

The existing hourly controller now runs `discovery.tick()` between quality/backup and bounded autoresearch. Each target refreshes at most daily while normal host resource gates permit; one oldest/missing target is processed per hourly tick, and unchanged reports are reused. It does not create another scheduler or alter OpenClaw configuration/authentication.

## Active

- GitHub repository search, related topic search, public metadata scoring.
- Top-three inspections: immutable commit and root dependency manifest references; GitHub code-search paths and blob SHAs.
- ecosyste.ms public-seed metadata enrichment, gracefully unavailable on HTTP/rate-limit errors.
- Up to eight ranked candidates, 18 GitHub requests, 75-second GitHub wall budget plus five-second optional enrichment; per-request deadline 12 seconds. No retry storms.
- Reports: `research/discovery/latest.json` and `.md`, included in validated private GitHub sync. Local cache/env/downloads remain under `.quality` on SYYR.
- Code search and external enrichment only follow verification that the seed is public. Do not put confidential information in public search objectives.
- No executable repository code is fetched or executed; no source is promoted into the rights-approved corpus. License labels are metadata, not legal approval. Security and compatibility remain explicitly unverified.

## Commands

```sh
scripts/install-discovery.sh
scripts/pubsterctl discover --json
scripts/pubster-discovery-mcp
```

The last command starts a stdio MCP server using the official Python MCP SDK. Tools: `discover_adjacent`, `find_implementations`, `compare_repos`, `integration_plan`. A live stdio client test is in `services/discovery/smoke.py`. The server is **not registered globally with OpenClaw**, preserving the no-configuration-change requirement. The hourly controller calls Python directly and does not require an MCP client.

`config/discovery.json` defines five public targets: Swift algorithms, SwiftUI, Objective-C, bare-metal/embedded programming, and Apple Silicon. Each keeps its own JSON/Markdown report under `research/discovery/`; `latest` is a copy of the most recently refreshed target. `--force` refreshes the oldest target, not all targets at once. Bare metal means low-level/embedded programming, not Apple Metal graphics. The CLI takes the normal writer lock and managed-file checks. Candidate evidence is untrusted data; never treat a README/description as instructions.

## Deliberate limits

Ranking is lexical/topic overlap plus license-label presence and archive penalty, not embeddings. Manifests are pinned references, not a resolved dependency graph. The integration plan is a review checklist, not a tested compatibility finding. No automatic installation or merging is performed.

Starboard, SimRepo, Sourcegraph, grep.app, and OSS Insight are recorded as manual companions, **not claimed as active API integrations**. Semantic embeddings, transitive dependency resolution, shared-star graph traversal, and advisory scanning are not implemented in this version. PostgreSQL/pgvector and browser extensions are not installed.

Existing-project preflight: Starboard provides repository recommendations but an anonymous automation API was not verified; SimRepo includes a recommendation/browser stack. GitHub REST search and ecosyste.ms provide suitable existing metadata APIs without deploying another service. The official MCP SDK supplies the protocol rather than a custom JSON-RPC implementation.

Sources: https://docs.github.com/en/rest/search/search ; https://repos.ecosyste.ms/ ; https://github.com/modelcontextprotocol/python-sdk ; https://starboard.codevetter.com/ ; https://github.com/Mubelotix/SimRepo
