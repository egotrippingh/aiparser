# Monthly scan calendar

Outcome: monthly choices 1–28 plus a square last-day flag; the flag may be selected
alone or with numbered dates. Selected dates survive save/reload and appear in
project-list and sidebar schedule labels. Legacy 29–31 remain explicit/removable.
Base on resume: production b165c429dc94b3de312072ec8cfa60f334723cc8, 2026-10-13.
The paused local UI was preserved in Git stash before integrating GitHub history.

History: PRs #49/#50 already published server last_day support. PRs #51/#52 added
provider pauses, actual-scan chart dates and native saved-answer rendering. PR #53
replaced the feed with Telegram news. Their source and delivery gates are retained.
Only control-center.tsx/css, the nearest frontend regression and generated cabinet
assets change in this completion; no server/schema/report/answer changes.

Keep: owner scope, revision CAS, dirty/error guards, immutable run snapshots,
unique scheduled slots, timezone/effective_from guards and old numbered schedules.
No automatic conversion that could add paid checks. New Project shares the controls.

Evidence: 84 frontend tests, lint exit 0 with warnings, TypeScript/Vite build;
8 existing schedule regressions pass with disposable SQLite/fake providers.
Browser QA: desktop and 390px; flag alone; enabled empty selection blocked;
explicit legacy removal; Space/Enter; save failure retains choices and allows retry;
save/reload; project-list label; 28+flag; disabled empty selection save/reload;
mobile scrollWidth=clientWidth=375, console errors/warnings absent.
Sol independent review and Astra release-risk review: no blockers.
No paid scans/payment/S3 requests.
Private proof: C:/codex-tmp/airate-schedule-calendar-20261013/.

Rollback: the previous production release already understands last_day and the
current migration head. Do not use a pre-#50/pre-news compatible application image.
Release: PR #54 merged into production 99d7fb34584eb9b12dab1378d7b73960fe4a86a5.
PR run 38357093941 passed on feature 94c00d4ec886dcdbce0a34ec1fa58dcb08985c83.
Production run 38357731853 passed Tests and build and Upload and activate verified
release; Verify public release failed. No delivery gate was changed or bypassed.
Google DNS still returns NXDOMAIN; Radix RDAP reports client hold, with expiration
2027-09-27. The user received REG.RU verification/block-removal instructions.
Remaining: remove registrar hold and verify public readiness/assets on this exact
production SHA; paid provider scans/payment/live S3 were not checked.
