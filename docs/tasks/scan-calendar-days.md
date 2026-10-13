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
Sol independent review: no blockers. No paid scans/payment/S3 requests.
Private proof: C:/codex-tmp/airate-schedule-calendar-20261013/.

Rollback: the previous production release already understands last_day and the
current migration head. Do not use a pre-#50/pre-news compatible application image.
Public readiness check currently fails TLS; Google DNS returns NXDOMAIN for the
public domain. PR #53 production run 38352484491 passed activation but failed its
final public-release check. User asked whether registrar problem was resolved.
Remaining: release CI, authorized publication, final live verification when DNS works.
