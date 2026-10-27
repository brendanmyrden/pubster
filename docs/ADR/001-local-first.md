# Local-first execution on external storage

2026-10-27: User authorized SYYR relocation, private GitHub pushes, and hourly bounded
maintenance/research. Later explicitly deferred Cloudflare. No cloud resources were
created. R2 was disabled (HTTP 403); no billing or terms accepted. Vercel tools/CLI
were unavailable; Supabase CLI reported no access token. No XAMPP/database server
installation is needed. SQLite and static Next export remain the chosen architecture.

Code/state/cache/build output use SYYR. Password verifier stays on the internal
filesystem outside Git with 0600 permissions. ExFAT has no reliable Unix ownership
boundary; do not move credentials there. External drive must remain mounted.

Reuse: SQLite FTS5, markdown-it-py, jsonschema, psutil, Next.js, Tailwind, shadcn/ui
Button pattern and Cloudflare Worker API contracts. No GPU autoresearch workload.
The current research runner permits numeric title-weight experiments only.
