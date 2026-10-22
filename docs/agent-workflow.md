# Small-context development workflow

Read this only for cross-layer, high-risk or multi-session work. Root `AGENTS.md` is
the everyday contract; subsystem instructions supply tests and invariants. Symptom →
doc map: [README.md](README.md). This adapts the supplied Go/microservice example to
one Python/React repository: no invented tracker, Go tools, shared-standard repository,
symlinks or unconditional agent fan-out.

## 1. Make a bounded work packet

For a short task, keep the packet in working context. For complex work save
`docs/tasks/<short-name>.md` (no secrets); update this same file instead of creating
repeated handover documents. Target 30–60 lines, excluding necessary evidence links.

```text
Outcome: observable before/after behavior, exact reproduction.
Base: branch + commit; pre-existing user changes.
Scope: entry point, affected symbols/files, shared callers/contracts.
Keep: ownership, durable evidence, billing, old-agent compatibility as applicable.
Acceptance: concrete case + expected result + runnable check for each requirement.
Steps: 2–5 independently verifiable slices, one active slice.
Evidence: exact command, result, tested commit/tree; existing failure vs new regression.
Remaining: unresolved requirement, actual blocker, next command.
```

If product details are missing, use existing behavior as the default for reversible
choices. Clarify a decision only if it changes authorization, data safety or acceptance;
work on independent steps while waiting. Do not invent requirements from the example.

## 2. Find the flow without buying context

- Known file: bounded `rg -n` and read the affected function plus callers/test.
- Unknown cross-file flow: query the local graph once, then verify suggested files in
  source. AST edges miss dynamic registration, DI, string routes and runtime behavior.
- Do not feed generated `web/`, node_modules, `.claude/skills`, entire graphs or historical
  briefs to the model. Instructions are layered; nested files must be explicitly read
  for their scope even when a tool starts from the repository root.
- If two searches fail, write a specific symbol/route hypothesis and test it. Do not
  dispatch broad architecture exploration merely because the current model is smaller.

Graphify is optional local cache (developer tool, not an app dependency). Missing
Graphify is not a blocker: use bounded `rg` and continue.

**Linux / Cursor Cloud (preferred when `graphify` is already on PATH):**

```bash
graphify extract . --code-only --no-cluster --max-workers 2
git rev-parse HEAD > graphify-out/source-commit.txt
graphify query "analysis_content" --budget 1200
graphify affected "analysis_content" --depth 2
```

Install only if needed:

```bash
python -m pip install --user uv
python -m uv tool install graphifyy==0.9.80
# ensure ~/.local/bin is on PATH, then:
graphify extract . --code-only --no-cluster --max-workers 2
```

**Windows / Codex (optional):**

```powershell
python -m pip install --user uv
python -m uv tool install graphifyy==0.9.80
python -m uv tool update-shell
graphify install --platform codex
```

After a Windows PATH update, reopen the shell or call
`& "$env:USERPROFILE/.local/bin/graphify.exe"`. Package name is `graphifyy`;
executable is `graphify`. Repo entrypoint: `.agents/skills/graphify/SKILL.md`.
No MCP server, paid semantic pipeline or automatic rebuild hooks.

Compare `graphify-out/source-commit.txt` to `git rev-parse HEAD` and inspect
`git diff --name-only HEAD` plus relevant untracked sources before trusting the graph.
Refresh after relevant edits or checkout; recreate the marker after a successful
refresh. `graphify-out/` is never evidence that a code change is correct. Default
install omits SQL AST; read `app/db/schema.sql` directly when needed.

Ponytail's minimal-code rule is already embedded in root `AGENTS.md`. Do not vendor
its library into this repo or load it automatically for documentation tasks.

## 3. Implement and check one slice

Start with a failing behavior check for a bug. Change the root cause across all shared
callers; preserve API/error contracts. Reuse pytest/Vitest and existing fake services,
not a new test framework. Run the nearest regression during iteration; broaden once
to subsystem gates when the final slice is complete. Do not rerun unchanged green gates.

CI parity setup uses Python 3.12 and Node 24.

Linux / Cloud:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-ci.txt
```

Windows:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r scripts/requirements-ci.txt
```

Use that interpreter for root Python checks. This is test setup; it does not fetch
Camoufox or install full Windows desktop dependencies. Desktop/manual execution follows
`README.md`. The full CI commands and process grouping are defined ONLY in
`.github/workflows/delivery.yml`; nested instructions are focused local gates, not a
replacement CI specification. Keep its separate agent test processes: broad collection
has previously reproduced baseline API smoke failures. Record a newly encountered
failure with a bounded reproduction on the base; never label it baseline by assumption.
Do not run tests against a real `DATABASE_URL`, production credentials or profiles.

## 4. Review according to risk

Always review the final diff for scope, callers, tests, ownership, retry behavior and
data preservation. Simple docs/cosmetic edits need no agent delegation. For money,
authorization, migration, durable scan/recovery or multi-layer changes use one independent
reviewer when delegation is authorized and available. Give it only the packet, base SHA,
diff and relevant test evidence; it must inspect changed code and return blockers with
file/line, failure scenario and missing check. Do not fork the whole conversation or run
three overlapping reviews. Fix findings and rerun affected checks only. If independent
review is unavailable, report that limit; do not claim independence for self-review.

The current model remains the default. Two failed fix/check cycles trigger a root-cause
reassessment and a smaller reproduction, not an unlimited retry loop. Escalate only
when concrete unresolved behavior warrants it and session authorization permits it.
This workflow reduces repeated context; it does not guarantee smaller-model correctness
or a measured percentage of token savings.

## 5. Deliver evidence, preserve production

Before staging: `git diff --check`, review the final file list and generated assets.
Push only when requested; verify the remote commit and its GitHub check status. A queued
or running check is pending, not green. Default PR target is `main`. Publishing website/
API requires a separately authorized PR into `production`; follow `deploy/DELIVERY.md`.
That branch triggers deployment after CI with backup/isolated restore, migration checks,
readiness and application rollback. Never weaken these gates to save tokens/time.
Installer publication is a separate Windows build/lifecycle/hash-verification action.

For release-state changes, update `PROJECT_STATE.md` with source branch/SHA and verified
facts; do not describe main-only code as deployed. End with outcome, actual checks,
commit/PR and remaining risk. On handover, leave only the current packet with next step
and evidence links; no full terminal dump or invented success claims.
