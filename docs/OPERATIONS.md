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
runs automatically yet; 20 GiB managed data hard-cap deferral must remain enabled.

`pubsterctl pause` / `resume` stops new work. `stop` currently pauses future work;
it does not terminate an in-progress short transaction. The supervisor enforces the
hard deadline. Do not kill all Python/Node processes.

Git synchronization verifies the expected remote, PRIVATE visibility, main branch,
no staged user edits, no unexpected dirty paths, and generated file hashes. It never
force pushes, resets, rebases, changes visibility, or overwrites unrelated files.
A diverged remote leaves work pending for review. Code changes are committed by the
operator; hourly commits include only approved generated corpus/research paths.
No GitHub Actions are installed. Export release attachments are separate from Git.

Research: one title-weight experiment per eligible tick, at most two/day, at most
300 seconds each. A corpus has a finite candidate set; after exhaustion the controller
reports NO_ELIGIBLE_HYPOTHESIS. Only strict MRR improvement without per-query regression
is retained. Evaluator copies and hashes are outside the candidate scope. No arbitrary
patches, model calls, training, credential access, or spending occurs in experiments.

Recovery: inspect last-run.json and hourly.log in external private state. Restore a
SQLite backup only into a disposable path first; run PRAGMA integrity_check. Rebuild
from the pinned source registry if necessary. Credentials are restored separately.
Cloud deployment is deferred; never deploy the placeholder-free but unbound Worker
config as a functioning corpus service. Provision and validate private bindings first.
