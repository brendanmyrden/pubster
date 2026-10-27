# Pubster engineering rules

Read README and docs/OPERATIONS before mutations. Keep code and bulky state on SYYR.
Keep secrets on the protected internal filesystem, outside Git. Never add transcripts.
No public hosting/billing is currently authorized for automatic maintenance.
Only explicitly reviewed source rights may enable acquisition/redistribution.
Tests and exports must pass before commits. Preserve human edits and never force push.
Research may change only configured numeric ranking weights; no executable proposals.

## Data-quality requirements (Josh, 2026-10-27)
Keep all new data-quality downloads, environments, temporary files, caches, logs,
OpenRefine projects and generated data under /Volumes/SYYR/Pubster/.quality.
Do not install these tools globally or use default home-directory storage.
Use DuckDB, Polars, Pandera, datasketch, Dedupe, Cleanlab and Great Expectations
for distinct quality functions; use OpenRefine for local human review. Preserve
immutable originals, code and source provenance. Similarity/outlier flags are
review suggestions, never evidence that a technical claim is false. Never silently
merge distinct source evidence. Pin library versions and index compatibility.

## OpenClaw-authenticated research (Josh, 2026-10-27)
Use OpenClaw's existing OAuth through its stateless inference CLI, not copied tokens.
Never change OpenClaw config, default models, auth, services or scheduler for this
adapter. Share no corpus text with the provider. One proposal/day maximum; numeric
title-weight proposals only, no executable output. Frozen evaluation decides retention.
Account quota and machine resources remain shared; zero usage impact is not promised.
