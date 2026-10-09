---
name: graphify
description: Navigate unfamiliar cross-file code relationships using Graphify's local AST graph, or build/refresh that graph when requested. Use for callers and impact analysis; known-file edits can use rg directly.
---

# Local code navigation

Follow the repository's `AGENTS.md` and `.graphifyignore`. Graphify is an index,
not an authority on runtime behavior or permission to run a paid extraction.

1. If `graphify-out/graph.json` exists and covers the current source, run one bounded
   `graphify query "<symbol or question>" --budget 1200` or
   `graphify affected "<symbol>" --depth 2`.
2. Verify relevant functions, actual callers and tests in source using `rg -n`.
   Dynamic routes/DI and some TS test code may not have useful AST edges.
3. If the graph is absent/stale and an index would help, run
   `graphify extract . --code-only --no-cluster --max-workers 2`.
   After success save `git rev-parse HEAD` to `graphify-out/source-commit.txt`.
   Check both that SHA and source changes/untracked files before later reuse.
4. If Graphify is unavailable or misses the symbol, continue with `rg`; do not
   install tools, rebuild repeatedly or read all `graph.json` to solve a one-file task.

Keep `graphify-out/` out of Git. Do not index private data, profiles, secrets,
generated assets or dependencies. SQL extraction needs the optional `sql` extra;
without it inspect schema sources directly. An absent graph result is not proof
that a caller/dependency does not exist.

Installation: official package `graphifyy`, executable `graphify`. This project
verified 0.9.80. In an already-open Windows shell use
`& "$env:USERPROFILE/.local/bin/graphify.exe"` if the PATH has not refreshed.
For installation/freshness detail, read `docs/agent-workflow.md` from repo root.
For advanced user-requested exports use `graphify --help` and the upstream docs
at https://github.com/Graphify-Labs/graphify; no cloud/LLM calls without scope and
cost authorization. Never enable hooks/watchers/MCP merely to answer a code question.
