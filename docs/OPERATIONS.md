# Operations

One OpenClaw command automation: `Pubster hourly maintenance`, cron `0 * * * *`,
America/Toronto, delivery none. It invokes `scripts/run-hourly.sh`, not an LLM turn.
The wrapper exits safely when the drive is absent. No wake or sleep settings change.
Actual scheduled occurrences are recorded by OpenClaw; a manual run is not one.

The supervisor owns one child process group. Bounds: 480 seconds wall, 90 seconds
aggregate live process CPU, 768 MiB aggregate live RSS; 2 MiB logs with four rotations.
These CPU samples are not a kernel CPU quota. A short-lived child can escape a sample;
network subprocesses have their own deadlines. Pipeline runs use only bounded Python
work and Git/CLI subprocesses. Backups retain four daily files. No raw-source cleanup
runs automatically yet; 20 GiB managed data hard-cap deferral is enabled.

`pubsterctl pause` / `resume` stops new work. `stop` currently pauses future work;
it does not terminate an in-progress short transaction. The supervisor enforces the
hard deadline. Do not kill all Python/Node processes.

Git synchronization verifies the expected remote, PRIVATE visibility, main branch,
no staged user edits, no unexpected dirty paths, and generated file hashes. It never
force pushes, resets, rebases, changes visibility, or overwrites unrelated files.
A diverged remote leaves work pending for review. Code changes are committed by the
operator; hourly commits include only approved generated corpus/research paths.
No GitHub Actions are installed. Export release attachments are separate from Git. Approved immutable bundles up to 25 MiB are uploaded only when the corpus changes, then downloaded and checksum-verified. A reserved daily 250 MiB transfer budget caps uploads plus verification downloads.

Research: the enabled OpenClaw adapter requests one numeric title-weight hypothesis
per day (America/Toronto), only on resource-eligible ticks. It uses the existing
OpenAI OAuth via `openclaw infer model run --local`; no tool-enabled agent, gateway
chat session, copied tokens, paid API-key fallback, or OpenClaw config mutation.
The provider receives only the research instructions and aggregate experiment
numbers, never corpus text or frozen test questions/answers. Corpus inference
remains disabled. Failures and timeouts consume the day's proposal slot.

Each experiment has a 300-second wall budget; auth checks and inference each have
120-second subprocess deadlines. One proposal at a time. Only numeric title_weight
values 0.25..16 in 0.25 increments are candidate-editable. Strict MRR improvement,
no per-query regression, and no development-set aggregate loss are required.
Auth, budgets, source rights, evaluator, Git targets and deployment are not editable.
The original deterministic grid remains available only when the adapter is disabled.
No eligible untried candidate means skip rather than manufacture progress.

Shared OpenClaw configuration is fingerprinted locally. Drift disables research until
review; it does not change or repair OpenClaw. OAuth profiles must be the effective
OpenAI auth route, with no API-key or token profiles mixed in. Account usage and host
resources are shared; this is not a claim of zero usage impact or isolated billing.
The CLI may refresh OAuth credentials through OpenClaw's normal auth lifecycle.
The existing hourly job/supervisor and Git sync are unchanged.

See docs/AUTORESEARCH.md for provenance, controls and test evidence.

Recovery: inspect last-run.json and hourly.log in external private state. Restore a
SQLite backup only into a disposable path first; run PRAGMA integrity_check. Rebuild
from the pinned source registry if necessary. Credentials are restored separately.
Cloud deployment is deferred; never deploy the placeholder-free but unbound Worker
config as a functioning corpus service. Provision and validate private bindings first.
