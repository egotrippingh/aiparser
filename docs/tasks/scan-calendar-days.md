# Schedule and measured chart dates

Outcome: monthly choices 1–28 plus a square last-day flag; charts contain only
recorded scan dates within the chosen report range.
Base: 07f8a58 on codex/project-report-services; clean tree, prior release c7e6c27.
Scope: server.control.Schedule/schedule_tick/project_values, control-center
schedule controls and labels, ReportView timeline filtering, nearest tests/assets.
Keep: owner scope, revision CAS, immutable run snapshots, unique scheduled slots,
timezone and effective_from guards; historical 29–31 choices remain explicit and
removable without silently adding paid checks. Local agent preferences stay intact.
Acceptance: last-day-only schedule accepts empty numbered days; invalid/duplicate
days and enabled empty choices fail; actual last day of 28/29/30/31-day months
runs once, including selected 28 plus flag and catch-up across a month boundary.
Unchanged historical schedule retains effective_from when other settings change.
Chart keeps zero and skipped/error scan dates, excludes unmeasured dates; empty,
single/multiple date and keyboard flows remain usable; selected services scope data.
Steps: failing regressions → minimal server/UI changes → gates and disposable
browser QA → independent review → authorized production release/live verification.
Rollout: publish server support first, with the old UI; then publish the new UI.
After a new empty/last-day schedule is saved, rollback must use an image with
last_day support. An older image rejects empty days and can halt schedule_tick;
the compatible server-only release becomes the previous image for the UI release.
Evidence: C:/codex-tmp/airate-schedule-days-20261012/ (private temporary fixtures).
Evidence so far: 5 server regressions failed before; 12 control tests pass after.
79 frontend tests passed before final review fixes; final gates are pending.
Sol review found project-list label and calendar-gap/empty-chart text issues;
fixed. Astra confirmed server behavior and required the compatible rollback image.
Remaining: final gates, browser QA, server-first and UI release.
