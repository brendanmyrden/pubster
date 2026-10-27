# Environment — 2026-10-27

macOS Intel, Node 26.12.0, Python 3.14.3. Project/state/tool caches on SYYR exFAT,
~921 GiB available after installation. Internal disk remains low; no large installs
or cache writes intentionally targeted there. ExFAT cannot host Unix-domain sockets;
Node test runner uses --import tsx to avoid tsx CLI IPC sockets.

Project-local pnpm 10.34.9; Next 16.4.3; Wrangler 4.153.0. All dependencies locked.
GitHub authenticated as brendanmyrden. Private pubster repo created and verified.
Cloudflare Worker/D1 connector readable, R2 disabled. Cloud explicitly deferred by user.
No connected Vercel tooling/auth found. Supabase CLI exists but has no authenticated token.
No model budget/provider configured. No paid usage enabled.
