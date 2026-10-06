## Project context and delivery

- Start with `PROJECT_STATE.md` for current facts and the next action. Read historical evidence only when a specific task needs it.
- Keep `PROJECT_STATE.md` short: current release, architecture, open checks and next action. Update existing facts after delivery; put detailed logs, checksums and release evidence in docs or the PR. Distinguish prepared, published and verified states.
- Small, low-risk copy or visual edits need one implementer and an appropriate check (for example, the changed viewport or frontend build). Do not start a full multi-agent review chain for them.
- Substantial behavior changes need relevant deterministic checks and independent review. Payments, authorization, migrations and possible data loss also need focused risk review. Keep CI and existing backup/rollback gates.
- Deliver through feature branches and PRs into `production`; follow `deploy/DELIVERY.md`. Keep `.env`, user data, browser profiles, `build/` and `dist/` out of Git.

### Verification commands (PowerShell, repository root)

Run the affected checks; full CI commands are in `.github/workflows/delivery.yml`.

- Server: `.\.venv\Scripts\python.exe -m pytest server -q`
- Agent: `.\.venv\Scripts\python.exe -m pytest tests/<affected_test>.py -q` (select existing tests for the changed behavior).
- Frontend: `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run build`.
- Scan timing: `.\.venv\Scripts\python.exe scripts/benchmark_scans.py --self-check` plus affected provider tests.
- Documentation: `git diff --check` and verify local links; no application build is needed for prose-only changes.

## Python development guardrails

Before changing Python in `app/`, `server/`, `desktop.py`, `scripts/` or tests, read the relevant sections of [Python antipatterns](docs/python-antipatterns.md). Apply them when implementing and reviewing the change. The catalogue covers language traps, async/concurrency, API validation, databases, billing, HTTP, security, Windows files/updates, browser scans, performance and tests. Research baseline: 2026-10-06, Python 3.12; check APIs against installed dependencies before using newer documentation examples.

- Trace the shared implementation and its callers before fixing a symptom. Reuse existing helpers, then stdlib and installed dependencies; avoid speculative abstractions and unrelated refactors.
- Do not introduce shared mutable defaults/state, late-bound loop callbacks, identity comparisons for values, or truthiness fallbacks that discard valid `0`, `False` or empty values.
- Validate external data explicitly. Type hints and `assert` do not validate production input; do not trust client-supplied ownership, prices, statuses, file paths or LLM output.
- Catch errors at the narrowest useful boundary, preserve causes and report failure honestly. Never silently turn failed scans, writes or payments into success, or swallow task cancellation.
- Keep blocking I/O and expensive CPU work off event-loop/UI threads. Own, bound and finish background tasks; use deadlines, safe cancellation and the existing scan timing policy.
- Keep database connections/sessions local to their owning thread/task and transactions explicit. Parameterize SQL; enforce race-sensitive invariants in the database. Do not hold transactions across remote calls.
- Preserve integer-kopeck accounting, server-side authorization, idempotency and the existing result/outbox/payment recovery flow. A timeout does not prove a remote write or charge failed.
- Close files, clients, responses, browsers and subprocesses deterministically. Bound request sizes, queues, retries, connection pools and caches; reuse clients within a safe lifetime.
- Never execute untrusted code or deserialize untrusted pickle, interpolate untrusted shell/SQL strings, disable TLS verification, or expose credentials/profiles in logs or artifacts.
- Preserve `app/config.py` data/resource path semantics, SQLite/WAL consistency, browser profiles and rollback. Validate archive members and update provenance before extraction/activation; do not overwrite user data during updates.
- Leave an appropriate deterministic regression check for changed behavior; use disposable state and existing pytest infrastructure. Follow the delivery/review gates above; prose-only changes need documentation checks.
- Apply the catalogue to touched behavior, not as authorization for a whole-project rewrite. A justified exception needs a concrete reason and a relevant check in the PR; add a `ponytail:` comment only for a deliberate shortcut with a known ceiling.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

Windows: if `graphify` is not yet on PATH, use `& "$env:USERPROFILE\.local\bin\graphify.exe"` in PowerShell. The initial graph indexes code only; refresh it without external model calls using `graphify extract . --code-only`.
