# Pubster autoresearch adaptation

This implements Karpathy's **propose → experiment → measure → keep/discard → repeat**
method using OpenClaw's existing authenticated model connection. It does **not** run
upstream `train.py`, train a language model, or require an NVIDIA GPU. Upstream is
pinned in `config/autoresearch-upstream.json` and checked out under the ignored
`.quality/autoresearch/upstream` directory on SYYR. `research/program.md` is our
own task-specific program, not permission to execute the upstream program verbatim.

## Pipeline

Approved-source ingestion → quality gate → deterministic export → model proposal →
local frozen evaluation → retain/reject → existing GitHub sync/release → next tick.

The hourly schedule remains unchanged. At most one model proposal/day is attempted;
other hourly ticks still maintain data and Git sync. The adapter reuses the same
resource checks, process-group watchdog and writer lock. It does not spawn another
chat agent or edit any gateway/session/default-model/scheduler configuration.

## Isolation boundaries

- `openclaw infer model run --agent main --model openai/gpt-6-astra --local` is a
  stateless completion, not a full chat-agent turn. No tools, chat history or MCP.
- Existing saved OAuth stays managed by OpenClaw. Pubster neither reads token values
  nor copies them, and never calls login/logout/refresh endpoints itself.
- Read-only auth status must show OAuth profiles as the effective OpenAI route,
  without API-key/token profiles. No alternate provider fallback.
- Only aggregate numerical results are sent. Corpus processing rights remain off.
- Output must be exactly a typed JSON proposal with a bounded numeric title weight
  and a short hypothesis. No code execution, shell commands or model-authored edits.
- Evaluation questions, answers and evaluation code are not exposed to the model.
- Attempts, including auth errors/timeouts, consume a slot reserved before invocation.
- A hash guard on the existing OpenClaw config fails closed on drift. Normal OAuth
  maintenance and account usage remain OpenClaw's responsibility. Credentials and
  auth configuration are not frozen or copied by the guard.
- This shares account usage limits and machine resources. A one-call/day limit is
  not a dollar-budget guarantee or a provider token cap; the CLI exposes no output
  token cap here. There is no authorization for new API-key spending.

## Controls and state

- Project configuration: `config/autoresearch.json` (`enabled: false` disables only
  model proposals and restores the prior deterministic grid).
- Pause only this adapter: create `.quality/autoresearch/paused`. Remove that marker
  to resume. `pubsterctl pause` still pauses all maintenance.
- Calls ledger, host-config guard and detailed last-run state live under
  `.quality/autoresearch/`. Project source, instructions and sanitized outcomes
  are committed. Credentials are not.
- `./scripts/pubsterctl research run-one --dry-run`: local preflight, no provider call.
- `./scripts/pubsterctl research run-one`: real attempt, with the project writer
  lock and managed-file checks. Respects the same daily limit; ordinary operation
  is via hourly maintenance and its existing Git sync path.
- The finite title-weight search space is deliberately narrow. More experiment
  families need new independently tested evaluators; this is not an endlessly
  self-modifying or unrestricted optimization agent.

## Sources

- https://github.com/karpathy/autoresearch
- Installed OpenClaw `docs/cli/infer.md` (tool-free local completion/auth semantics).
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions

Research uses existing authenticated capacity and contributes to the account's
applicable usage. No separate entitlement is asserted by the integration.
