# Docs index

Open **one** row that matches the task. Do not preload briefs, release notes or
`PROJECT_STATE.md`. Everyday contract stays in root `AGENTS.md`.

## Symptom → file

| When you need… | Read |
|---|---|
| Cross-layer / multi-session work packet, Graphify install | [agent-workflow.md](agent-workflow.md) |
| Saved Windows sessions / portable→installer data paths | [session-preservation.md](session-preservation.md) |
| Agent EXE version, in-app update, installer publication | [updater.md](updater.md) |
| Coinso top-up / payment webhook setup | [coinso.md](coinso.md) |
| Plain-text answers vs display / matching | [answer-readability.md](answer-readability.md) |
| Managed check UUID vs local query IDs | [managed-check-identifiers.md](managed-check-identifiers.md) |
| Report cell symbols (✓ / — / !) | [report-status-symbols.md](report-status-symbols.md) |
| Error reason in reports / old-agent gaps | [report-response-diagnostics.md](report-response-diagnostics.md) |
| Project feedback → future inference (not history rewrite) | [scan-feedback.md](scan-feedback.md) |
| Empirical inter-query delays / fast profile | [scan-delays.md](scan-delays.md) |
| Sentry DSN wiring (ops) | [sentry.md](sentry.md) |
| Sentry acceptance / sanitization scope | [sentry-brief.md](sentry-brief.md) |
| Cabinet draft/evidence UI defects | [frontend-hardening.md](frontend-hardening.md) |
| Landing cleanup / agent presentation on site | [landing-agent-cleanup.md](landing-agent-cleanup.md) |
| Active task packet (if present) | [tasks/](tasks/) |

## Historical briefs (only if continuing that release)

| Topic | Brief | Release notes |
|---|---|---|
| Durable capture + adaptive pacing | [scan-pipeline-brief.md](scan-pipeline-brief.md) | [scan-pipeline-release.md](scan-pipeline-release.md) |
| Scan throughput follow-up | [scan-throughput-brief.md](scan-throughput-brief.md) | [scan-throughput-release.md](scan-throughput-release.md) |
| Google consent + dated «не проверялось» | [google-consent-report-brief.md](google-consent-report-brief.md) | — |
| Provider E2E status notes | [provider-e2e-brief.md](provider-e2e-brief.md) | — |
| XMLRiver server operator steps | — | [xmlriver-cloud-release.md](xmlriver-cloud-release.md) |

Release-state narrative for operators lives in root `PROJECT_STATE.md` — read the
short current state once at task start; reread for version, deployment, compatibility
or open-risk questions.
