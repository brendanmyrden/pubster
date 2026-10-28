# Pubster capability intelligence

Orchestrated by [@joshfisidi](https://github.com/joshfisidi).

## What changed

The existing discovery entry point, scheduler and 251-topic catalog are preserved.
`pipeline/pubster/intelligence/` adds a SQLite ledger, adapters, pinned inspection,
evidence-aware ranking and an operator interface. No replacement corpus database,
new service, paid provider, model call, hosted deployment, or automatic installation.
The original discovery implementation remains available by setting `enabled:false`
in **config/intelligence.json** (inspect/merge configuration before changing it).

The seven rotating modes are Hidden Gems, Capability Expansion, Performance
Extremes, Unusual Engineering, Composable Infrastructure, Forgotten Engineering,
and Adjacency. Each can return leads; this does not mean every lead is useful.
A bounded manual smoke report for each is under `research/discovery/mode-*.json`.

## Search strategy

Two cheap queries precede a rotating enrichment technique:

- Topic coverage remains an eligibility signal, not the final value score.
- A versioned concept dictionary maps intended functionality to cross-language
  capability queries and symbols. This is deterministic semantic **intent expansion**,
  not learned embeddings or an LLM semantic search service. Unsupported concepts
  fall back to sanitized purpose terms. No private/corpus text is sent to a provider.
- Code-symbol searches, pinned manifest dependency links, reverse code references,
  fork comparison (independent ahead commits), arXiv metadata/implementation links,
  issues, GraphQL discussions, release links, contributor repositories, and
  alternative implementation searches rotate across scans.
- Dependency references are evidence of a relationship, not a complete package
  manager resolution. Reverse references need review to confirm actual dependency.
  Fork ahead counts establish divergence, not its technical importance.
- Scholarly results can be empty or unavailable; paper-related GitHub fallback hits
  remain unverified until the paper/implementation relationship is inspected.
- Contributor adjacency is not endorsement. External descriptions are inert data.
- Hidden Gems samples ascending-star results without a hard star ceiling. The other
  modes retain popular projects; an obscure subsystem can exist in a popular repo.
- Forgotten Engineering searches archived projects but never penalizes their value
  score solely for archive status. Maintenance risk is recorded separately.
- Adjacency starts from rights-approved repositories and uses a persistent frontier,
  at most three hops and 500 frontier entries. Canonical IDs prevent graph cycles.

A tick handles one topic, not all 251. Mode and technique rotation are global;
coverage is a backlog, not a claim that every mode runs on every topic each day.

## Budget and persistence

Per invocation: 18 network requests total (including scholarly metadata), 75 seconds,
2 MB/response, 12 MB aggregate response bytes, 0.25-second GitHub request spacing,
eight reported leads and one deeper inspection by default. The pre-existing hourly
supervisor remains the outer resource bound. No new recurring work is scheduled.
An API failure/empty response is reported, not replaced by invented evidence.

The local ledger is `.quality/intelligence/ledger.sqlite3`, outside Git, on SYYR.
It stores search cursors, task checkpoints, repository/revision snapshots, graph
edges, API cache, immutable score evaluations, criteria versions, requests, and
append-only review/outcome events. A killed task resumes after its last committed
checkpoint; an in-flight API call can repeat. Cached completed responses avoid
repeating most requests. Search pages rotate through at most three pages.
The response cache is bounded to 128 entries/32 MB; pinned inspection metadata and
historical evaluations persist. No candidate source checkout or code execution.

The additive schema migration saves byte-exact copies of pre-upgrade reports and
existing review/rights records under `.quality/intelligence/legacy-v1`. It never
rewrites the rights registry or deletes old decisions. Original per-topic reports
are refreshed normally; migration copies preserve their pre-upgrade form. Failed
refreshes preserve the previous successful report in the existing private cache.

## Evidence and two-level ranking

The exact weights are versioned in `config/intelligence.json`:
power 20, usefulness 20, novelty 15, composability 15, evidence 10,
underexposure 10, sovereignty 10. Scores sum to 0–100.

Repository assessments and individual implementation-file assessments are separate.
Pinned source paths, hashes, declaration line numbers, manifest paths, tests and
benchmarks are recorded. A declaration or a benchmark filename is not proof of
behavior or performance. Raw source stays in the ignored response cache; public
reports contain provenance and structural observations, not copied source files.

- **Verified**: an operator records independent verification and its evidence.
- **Source-supported**: a pinned implementation was inspected, not executed.
- **Claimed**: project metadata/README claims, not independent confirmation.
- **Speculative**: proposed build/integration opportunity, not demonstrated.

Automated discovery never assigns Verified. Unknown performance/novelty earns
zero, not a guess. High power requires reviewed mechanisms or reproduced benchmarks;
README superlatives and stars alone earn no power points. Preliminary manifest and
source availability can earn limited composability/usefulness/evidence credit.
An overall score is an evidence-backed lower bound, not a verdict on unseen code.

Underexposure compares at least three peers of the same language, three-year
creation-age bucket and query-inferred purpose. It does not alter usefulness.
An inadequate cohort earns no underexposure credit and says why. Cohorts are local
samples, not a GitHub-wide popularity model. Timestamps describe commits/pushes;
**last meaningful update remains unknown** without change review.

Maintenance, security, license compatibility, effort, confidence and corpus overlap
are separate fields. Repository overlap is exact canonical identity; capability
novelty/overlap requires semantic comparison, never inferred from a new repo URL.
Metadata-only leads without a commit remain Discovered, awaiting enrichment. A
significant source-backed finding has a pinned SHA and source links. The default
inspection samples one source file and does not claim whole-repository review.

## Operator workflow

```sh
./scripts/pubsterctl intelligence status
./scripts/pubsterctl intelligence scan --mode hidden-gems \
  --seed apple/swift-collections --objective 'Swift high-performance collections'
./scripts/pubsterctl intelligence history --repository owner/repository
./scripts/pubsterctl intelligence record --record .quality/review.json
```

Scans use the existing writer/discovery locks and generated-file ownership checks.
They write only the explicit `research/discovery/` report family and local ledger.

Review JSON requires repository, revision, kind, actor, rationale. Kinds:
`reviewed`, `verified`, `approved`, `rejected`, `prototype`, `integration`,
`false_positive`, `capability_introduced`, `feedback`.
Evidence entries require URL, status and rationale. Assessments can explicitly
attest to `mechanism_reviewed`, `use_case_reviewed`, `alternative_comparison`,
`benchmark_reproduced`, `integration_success`, `offline_build`, `executed`.
Execution claims require Verified evidence plus an execution record; the engine
records the operator's attestation, it does not execute the supplied command.

The lifecycle is Discovered → Enriched → Scored → Reviewed → Verified →
Approved/Rejected. Enrichment/scoring occur together after a pinned inspection.
Verified requires a current review and verification evidence. Approved requires
current verification plus license review. Rejection is reversible through a new
review; earlier decisions remain in event history. Even an Approved intelligence
finding **does not** edit rights-policy.json or insert anything into the corpus.
The existing separately reviewed, commit/document/license-pinned admission process
is still required.

Feedback with `purpose_concept` (a configured concept ID) and `search_terms` updates
future query terms with explicit provenance; ranking-weight feedback remains a
pending proposal. Canonical criteria never change automatically. A criteria change
must use a new scoring version; reusing a version for different weights/intent
concepts/threshold fails closed. Historical scores and evaluations remain available.

## Effectiveness and limitations

Reports/status expose candidate counts, preliminary source-supported relevance,
high-value yield, duplicate inspections, review false positives, verified hidden
gems in the last 30 days, introduced capabilities, prototype completions,
integration outcomes, request/byte costs, duration, errors and verification counts.
Unavailable denominators produce null, not invented success rates. No prototype or
integration is counted without an outcome event. No monetary cost estimate is
invented; this engine makes zero paid/model API calls.

The engine provides a bounded evidence funnel, not autonomous proof of exceptional
engineering. Benchmark execution, complete source review, platform builds, full
package graphs and capability-level equivalence still require deliberate review
and appropriately scoped prototypes. No discovered code executes automatically.

## Memory diagnostic, separate from discovery

The requested `openclaw memory status --index --agent main` reported an existing
`fts-only` index versus configured `text-embedding-3-small`; its attempted embedding
indexing failed with `429 credit_balance_exhausted`. Semantic memory is unavailable.
No configuration, original memory data, credentials or scheduler were changed by
this upgrade; no rebuild retry or paid-credit purchase was attempted. This failure
does not prevent the GitHub discovery ledger from operating.

A [worked source review](INTELLIGENCE-EXAMPLE.md) demonstrates why low recognition
and performance claims do not automatically make a project a hidden gem.
Reviewed `capability_findings` explicitly record new/improvement/redundant/unknown
relationships with pinned source URLs and rationale; query feedback and subsequent
ranking consume recorded reviews without overwriting historical evaluations.
Scoring registry fingerprints also include the ranking implementation itself.
