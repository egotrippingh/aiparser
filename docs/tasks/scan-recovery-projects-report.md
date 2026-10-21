# Scan recovery, project navigation and report presentation

Base: production c43a39f5805cd2aed2e25525af74c6875739c8ab.
Branch: codex/scan-persistent-retry. User authorized all tasks and deployment.

## Scope and acceptance

1. Complete-policy scans retry uncertain submissions beyond three attempts, with
   durable delay, stable check/reservation and a single user charge. Existing
   retry_exhausted tasks recover automatically. Pause/stop and callback fencing
   remain effective. No fabricated successful results or migration.
2. Check all five providers for queue blocking. Healthy services must finish while
   another waits. Accepted pending AI tasks yield worker slots and resume by ID,
   without resubmission. Preserve legacy behavior and resource bounds; distinguish
   this from finite capacity during slow in-flight HTTP/model calls.
3. Projects page has no selected project context or sidebar. Header search/select
   opens the selected project's dashboard. New column immediately after project
   name shows the shared filling scan circle or Ready for checks; remove old
   Status column. Circle opens current scan details. Preserve role authorization.
4. Report's third metric and query percentage/dynamics compare first to last
   actual scan date in selected period, like explicit two-date comparison. User
   confirmed percentage of mentions, not ranking position. Respect date/service/
   query filters and scrolling window; no false change with fewer than two dates
   or missing endpoints. Existing period totals and exports remain valid.
5. Normalize Gemini/GPT answer display: escaped punctuation, visible strong tags,
   readable URL labels including Cyrillic/IDN and removal of verbose text fragments
   in labels. Yandex sources appear in the common Sources block. Preserve original
   evidence, code, brand highlighting, safe links and escaped untrusted HTML.

## Delivery gates

Focused regressions, complete server suite (PostgreSQL in CI), frontend tests,
lint/build, desktop and narrow disposable browser checks, independent Sol review
and Astra risk review; PR into production, green exact-SHA CI, existing backup/
isolated restore and deployment gates, live readiness, Geosoft Dent completion.
No secrets, user DB or browser profiles in Git. Update PROJECT_STATE after delivery.

## Prepared validation

- Local frontend132 tests, lint and final build pass after the IDN addition. Source labels use pinned punycode2.3.1 (no transitive dependencies)
  instead of a handwritten decoder. Original href and evidence remain unchanged.
- Seven queue regressions pass (all five providers and known-handle reuse). Final
  lazy-recovery subset: seven pass, two PostgreSQL cases deferred to CI. Two new
  endpoint report regressions pass; date-window/SQL-bound checks remain in CI.
- Sol and Astra independent reviews passed after lazy exhausted-task recovery,
  period filter preservation and IDN fixes. No schema/deployment-script change.
- Disposable desktop/narrow browser checked navigation, circle/details, endpoint
  comparison and Gemini/ChatGPT/Yandex source presentation. Evidence and full logs
  are outside Git in the local scan-retry-20261021 directory. CI/deploy pending.
