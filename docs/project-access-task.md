# Project access delivery

Prepared feature branch: `codex/project-access`. Base: current `origin/production`
`112cd86b7133c30a32938dc5d0ae0320165687d4` (2026-10-19).
This is a prepared implementation and disposable preview, not a published release.

## Agreed scope

- Show and copy the existing permanent project UUID; preserve old IDs and data.
- Add a separate Russian «Доступ» tab with the existing Lucide `UserPlus` icon.
- The creator is the immutable owner. Only the owner grants, changes and revokes
  access, by the exact normalized email of an existing registered user.
- Editor: settings, queries, schedule, feedback and scan controls; no project
  deletion or membership management. Viewer: results, reports, sources, screenshots
  and exports; no mutations. Shared projects appear in the recipient's list.
- User explicitly chose payment from the owner's balance for editor scans and
  schedules. Preserve owner pricing, promo credits, reservations and recovery.
- Keep the existing experimental recompute/clarification eligibility; sharing
  does not grant admin or device capabilities.

## Affected flows and acceptance

1. Project list/header and project switch: stable full ID, copy feedback, clear
   role, access tab retained when switching, responsive keyboard navigation.
2. Access form/list: add existing email with editor/viewer role, change role,
   revoke, handle duplicate/self/unknown account and failed requests honestly.
3. Project API: database-constrained memberships, explicit read/edit/owner checks,
   archived/revoked projects unavailable; preserve revision conflicts and device
   boundaries. Serialize membership changes and project writes where required.
4. Reports/detail/export/screenshot: bind each result to authorized project and
   project owner. No cross-project or cross-owner check-ID leaks. Keep private
   no-store responses, 90-day screenshot retention and expiring signed URLs.
5. Scan quote/launch/commands: use owner's wallet, pricing, credits, devices and
   feature eligibility. An editor's admin status cannot change owner's pricing.
6. Migration: additive reviewed Alembic revision and legacy admission update;
   verify fresh/previous schemas and data preservation on disposable databases.

## Delivery gates

One implementation writer (Terra), independent correctness review (Sol) and
authorization/money/migration risk review (Astra). Run focused regressions while
iterating, then full server tests, frontend tests/lint/build on the final source.
Exercise owner/editor/viewer/revoked states with disposable data at desktop and
narrow widths; report unavailable verification honestly. Refresh Graphify once
after source completion. Deliver a PR into `production` and interactive preview.
Publication requires separate user approval plus existing backup/isolated restore,
migration admission, readiness and compatible application rollback gates.

Signed URLs already issued may remain usable for up to 300 seconds after revoke.
No invitation emails, public links, ownership transfers or live account changes.

## Migration and release admission

New head: `20261019_project_members`, parent `20261015_email_registration`.
The migration adds one table and its index; it does not rewrite project IDs,
results, users, wallets or existing memberships. The previous application can
ignore the added table, but its startup migration-head check still requires a
separately prepared rollback image that recognizes the new head.

Before an authorized release, follow `deploy/DELIVERY.md`: retain a fresh backup,
restore into an isolated database, compare existing table contents, upgrade and
run metadata/readiness checks there, prepare the compatible rollback image, and
admit the new head explicitly. Never bypass the deployment head gate or downgrade
the live database. Test owner/editor/viewer and revocation after activation.

An action accepted before revocation may complete; existing runs and the saved
schedule continue for the owner. Revocation does not stop/refund an accepted run.

## Verification evidence

Implementation and deterministic test source: `8d1954add9ca2202f5e802a5cd7278d4be917435`.
[PR #75](https://github.com/egotrippingh/aiparser/pull/75) tracks the final backend,
PostgreSQL concurrency and image gates.

- Independent correctness and authorization/money/migration reviews closed their
  findings. Regression tests cover owner promo refunds, fresh worker state,
  owner feature eligibility, archived runs, device assignment and private evidence.
- Frontend: 119 tests passed, lint exited 0 (existing warnings), production build
  exited 0. Browser checks covered unknown email, add/change/revoke, project switch,
  all roles, ID copy, read-only detail/export, owner-funded quote, keyboard and 390px.
- Local full server run before the final test fixes: 347 passed, 36 skipped and
  four failures. All four passed after the targeted fixes: the migration expectation
  includes the new empty table; three XML-only timing tests now isolate an unused
  HTTP client. Original timing limits/assertions and production scan code are unchanged.
- The new focused authorization suite passed 3 tests locally; its 3 PostgreSQL
  race cases require the CI database. SQLite is not evidence of PostgreSQL locking.
- Graphify AST-only update succeeded on the source commit above (4533 nodes,
  13332 edges); local index/provenance files remain ignored by Git.

Legacy attachments without verifiable run/project provenance remain visible to
the owner; members receive the saved result but not unproven check/capture data.

## Published release

The user explicitly authorized deployment after reviewing the preview.
[PR #75](https://github.com/egotrippingh/aiparser/pull/75) merged as
`08053d4fcd4aa26d95952c2adb8ba23b44ff06a8`.
[Production CI](https://github.com/egotrippingh/aiparser/actions/runs/39321679472)
passed all jobs, including 383 server tests with PostgreSQL races, 119 frontend
tests, image smoke checks and deployment. HTTPS readiness returned this exact SHA;
the healthy container and image labels matched. Public cabinet JS contains the
access interface; unauthenticated member read/write/revoke requests return 401.
Role flows were checked with disposable preview data, not real production accounts;
no paid scan or sharing of a real project was used as a release probe.

Independent Astra review accepted the exact one-off operator scripts. Both the
restored-copy rehearsal and drained live migration preserved all 32 existing
tables' columns and canonical row hashes. Fresh backup/isolated restore and
compatible fallback readiness passed. Live backup is
`aiparser-20261019T204237Z-854985.dump`; operator proofs and saved fallback archive
remain private on the VPS in `/opt/airate/releases/access-20261019`.
See [rollback instructions](../deploy/DELIVERY.md#project-sharing-schema-on-19-october-2026).
The migration-head gate, restricted CI account and backup gates were retained.
Backups remain VPS-local; off-VPS protection is not verified.
