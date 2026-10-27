# Local data quality

User requirement, 2026-10-27: keep **all new data-quality storage inside
`/Volumes/SYYR/Pubster`**, including tools, dependencies, installers, temporary
files, caches, reports, quarantine and OpenRefine projects. The ignored `.quality/`
directory contains that runtime state. No global installers, Homebrew, cloud
accounts, paid inference or telemetry are used by this integration.

The original canonical SQLite database and raw archives remain in the existing
`/Volumes/SYYR/Pubster-state` directory; this update does not relocate that data.
Credentials remain outside Git. Nothing from `.quality/` is committed.

## Components

- DuckDB: bounded in-memory SQL grouping of exact content hashes.
- Polars: metadata normalization and Parquet/CSV review artifacts.
- Pandera: required fields, identity uniqueness, rights and value constraints.
- datasketch: deterministic five-token MinHash/LSH candidate search, followed by
  exact shingle Jaccard verification. Library version, seed and parameters recorded;
  indexes rebuilt per new job, never mixed across incompatible versions.
- Dedupe: actual string/exact-field comparison distances on candidate pairs.
  No learned merge probabilities without reviewed match/distinct training pairs.
- Cleanlab: numeric structural outlier scores (length, lines, code fences, title
  length). These are **not** technical truth judgements or mislabeled-data claims.
  Label-quality analysis still needs real labels and out-of-sample probabilities.
- Great Expectations: in-memory validation of uniqueness, provenance URL presence
  and approved rights, with reporting. Telemetry disabled.
- OpenRefine: local review workspace and importable metadata CSV; never writes
  corrections back into the canonical database automatically.

## Run

```
./scripts/pubster-quality
./scripts/pubster-quality /Volumes/SYYR/Pubster/.quality/staged/INPUT.jsonl
./scripts/pubster-openrefine
```

OpenRefine binds only `127.0.0.1:3334`; it is not a remotely deployed website.
Import the current job's `openrefine-review.csv`. Review artifacts retain chunk IDs,
source URLs and revisions. Stop OpenRefine when finished to free memory.

`quality-env.sh` redirects application caches and temporary files to SYYR and limits
numeric library threads to one. Java user-home, temporary files, preferences and
OpenRefine workspace are explicitly local. The portable OpenRefine Java distribution
and portable Adoptium JRE avoid the macOS installer mount restriction. Published
SHA-256 digests are checked before extraction. macOS AppleDouble sidecars must be
kept out of OpenRefine's JAR directories (they look like broken JARs to Jetty).

The quality subprocess runs before committing new source chunks and before export.
It also runs on eligible hourly maintenance ticks. Existing source-provenance,
license evidence, raw-hash and secret checks remain mandatory on export.
A schema failure quarantines the original candidate batch and leaves previously
accepted records intact. Duplicate/anomaly flags preserve both sources for review.

Jobs use content/code/dependency fingerprints, a nonblocking process lock and
cached reports. Batch limits: 5,000 records, 40 MiB serialized input, 20,000 candidate
pairs. DuckDB memory: 128 MiB. Worker timeout: 180 seconds; the existing aggregate
hourly watchdog remains unchanged (768 MiB, 90 sampled CPU seconds, 480 wall seconds).
Too-large or failed batches stop publication; they are not silently truncated.

No automatic factual rewriting, trained entity merging, Swift compilation,
contradiction resolution, remote reconciliation, MCP service or new web dashboard
is claimed by this initial integration. These require separate implementation and
validation. The original website and hourly GitHub synchronization remain in place.

## Reproduce the Python environment

Run `./scripts/install-quality.sh` with Python 3.13 already available. Dependencies
are pinned in `services/data-quality/requirements.lock`. On this exFAT volume,
setuptools counts `._*.whl` sidecars as additional wheel artifacts. The narrowly
scoped `quality-build-compat.py` excludes those names in the project-local
build backend and wheel archive writer. No global package is patched. Source build isolation is disabled
only after installing the pinned build dependencies into this dedicated environment.

## Upstream references

- https://duckdb.org/docs/stable/clients/python/overview
- https://docs.pola.rs/user-guide/installation/
- https://pandera.readthedocs.io/en/stable/polars.html
- https://ekzhu.com/datasketch/minhash.html
- https://docs.dedupe.io/en/latest/API-documentation.html
- https://docs.cleanlab.ai/stable/cleanlab/outlier.html
- https://docs.greatexpectations.io/docs/core/configure_project_settings/toggle_analytics_events/
- https://openrefine.org/docs/manual/running

## Verified initial run

See `reports/data-quality-launch.json`: 262 records passed, 15 tests passed,
271 export checksums verified. One exact-duplicate group and one near-duplicate
pair were preserved for review. The uncalibrated structural OOD threshold (<0.2)
flagged 100 records: these are triage signals, not 100 errors.

OpenRefine's API confirmed 262 imported rows. The checksum-verified upstream
3.10.1 release asset identifies itself as `3.10-SNAPSHOT [TRUNK]` via its API;
both identifiers are recorded rather than silently equated. Browser interaction
was not verified. Run `scripts/openrefine-import.py` with the quality Python
after starting OpenRefine to idempotently import the latest metadata review job.
Install portable review tools with `scripts/install-review-tools.py`; its pinned
archive manifest is `services/data-quality/tools.lock.json`.
