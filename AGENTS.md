# AIRate agent contract

Mandatory for every coding agent. Current user instructions take precedence.
Communicate in Russian; keep code and commit messages consistent with nearby files.

## Start small

1. Run `git status --short --branch`. Preserve changes you did not make.
2. Identify one observable outcome, the affected subsystem and its acceptance check.
3. Read the matching nested `AGENTS.md` BEFORE editing, including when working from root.
4. Locate the entry point, changed symbol, all callers and the nearest regression test.
   Use bounded `rg -n` searches. Read complete affected functions, not the entire repo.
5. Implement the smallest complete fix, run the required checks, inspect the final diff.
   Never call a task done while an acceptance criterion remains unresolved.

## Project map — load only the affected row

| Scope | Entry points / flow | Rules and reference |
|---|---|---|
| Windows agent | `app/main.py`, `desktop.py`; `app/control_agent.py` → `app/scanner/orchestrator.py` → adapters → durable capture → analysis/result/outbox | `app/AGENTS.md`; session changes: `docs/session-preservation.md` |
| Server | `server/app.py`; `server/control.py` runs/devices; `server/models.py` storage; `server/reporting.py`, `server/scan_feedback.py` reports | `server/AGENTS.md`; `server/README.md` for setup |
| UI | `frontend/src/` React/TypeScript; `frontend/vite.config.ts` builds the tracked `web/` directory | `frontend/AGENTS.md`; `PRODUCT.md`, `DESIGN.md` for interface work |
| Delivery | `.github/workflows/delivery.yml`, `deploy/`, `scripts/build-*.ps1`, `scripts/publish-agent.py` | `deploy/DELIVERY.md`; `docs/updater.md` for agent releases |

`main` is development; pushes to `production` can deploy. Feature branches use
`codex/<short-name>` and PRs target `main` unless the user explicitly requests a release.
Do not retarget or merge a PR, push to production, publish an installer, run a live
migration or delete user data without authorization for that action. Reuse authorization
already given; do not ask again. A code push alone is not a production-release request.

## Token budget and implementation

- Simple task: execute directly, no plan file, no agents, no whole-repo audit.
- Cross-layer, risky or multi-session task: read `docs/agent-workflow.md`; split into
  independently testable steps. Carry only the current step's files and evidence.
- Reuse existing code → stdlib/native platform → installed dependency → minimal new code.
  No speculative abstractions, sweeping formatting, unrelated fixes or new frameworks.
- Batch independent reads; cap search/log output. After two unproductive searches,
  narrow to a concrete symbol or test. Do not repeat unchanged reads or green checks.
- Use the current model by default. Stronger models and delegation are not automatic
  solutions to missing context; use a smaller task and a reproducible failing check first.
- Two failed fix/check cycles: stop blind editing, record the failure and reassess the
  cause. Ask only if a missing decision/access blocks progress; continue independent work.
- Do not load all skills, old briefs, histories or `PROJECT_STATE.md` on every task.
  Read release state only for version, deployment, compatibility or open-risk questions.
- Ponytail's minimal-code approach applies without weakening validation, authorization,
  data preservation, error handling or accessibility. An installed skill is optional
  context, not a reason to run a large workflow for a small edit.

## Graphify — local navigation, not proof

For unknown cross-file relationships, use an existing fresh graph first:
`graphify query "<symbol or question>" --budget 1200` or
`graphify affected "<symbol>" --depth 2`. Verify the suggested callers in source with `rg`.
For a known file/one-symbol edit, go straight to source. Never read all `graph.json`.
Build only if useful: `graphify extract . --code-only --no-cluster --max-workers 2`.
After relevant source changes or a branch switch, refresh before trusting graph results.
The graph is ignored local cache; missing Graphify is handled with `rg`, not a blocker.
No paid semantic extraction, cloud upload, background watcher or automatic hooks by default.
See `docs/agent-workflow.md` for portable installation and freshness commands.

## Non-negotiable completion gate

- Bug: one regression check fails before the fix and passes after. New nontrivial logic:
  test observable behavior, including the relevant failure case, in the existing suite.
- Run the affected scope's gates from its nested instructions. Pure docs: verify paths,
  commands and `git diff --check`; no browser, build or application suite required.
- Local passing tests are not live provider, PostgreSQL, S3 or payment evidence. State
  skipped checks and baseline failures precisely; never weaken tests to obtain green.
- Never print or commit secrets, cookies, `.env`, real DBs, profiles, screenshots or logs
  with user answers. Test with temporary data and fake external services by default.
- Check `git diff --check` and `git diff --stat`; stage only task files. No force push,
  destructive reset, bypassed CI, blanket staging or unrelated dependency upgrades.
- For requested push/merge, verify remote SHA and CI on that SHA. Report pending/failed
  CI honestly. CI job definitions are authoritative; preserve existing delivery gates.
- Final reply: outcome, actual checks, commit/PR link and material remaining limitation.
  Keep it short; do not paste tool logs or claim quantified token/accuracy improvements.
