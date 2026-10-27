# Security boundaries

The supplied password has a salted scrypt verifier outside the repository. Production
verifier is not in test fixtures. No deployment secret was sent to a cloud service.

The Worker defaults to closed without required bindings/secrets. Its tests cover
wrong/correct synthetic passwords, rate limit before KDF, secure cookies, duplicate
cookies, credential version invalidation, logout/token reuse, CSRF and Origin checks,
path normalization, unauthenticated GET/HEAD/Range, and bounded FTS/ranges.

Production crypto CPU/memory/concurrency, remote D1 behavior and browser interaction
remain unverified until cloud deployment. The static frontend holds no corpus. Markdown
uses react-markdown with raw HTML skipped, images disabled, and only HTTPS links.
Build-time CSP hashes permit exact Next bootstrap scripts, not arbitrary inline scripts.

Only two allowlisted public repositories may be fetched. Raw HTTPS requests reject
redirects, credentials, arbitrary hosts and ports; response bytes and requests are capped.
License evidence is required. Unknown candidate rights stay unknown. Upstream code is
never executed during ingestion. Oversized sections are excluded rather than split
through code fences. No arbitrary URL, shell, or web administration endpoints exist.
