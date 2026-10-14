# Promo codes and query import help

Outcome: admin creates codes with nonnegative scan counts per current service;
users redeem at registration or top-up, once per code/account. Scan credits pay
only for their service and never for saved-answer recomputation.
Base: bf837fb66a1571f1f74f7ac81d51f837f0017d38; initially clean tree,
codex/scrapeless-webhook ahead of its remote by one existing commit.
Work branch: codex/promo-codes. No push/deploy authorization.

Scope: models/new Alembic revision, migration admission, auth registration,
admin API, wallet redemption, checks reserve/release, cloud worker callers,
project quote, cabinet/admin/top-up forms, query import help and built web.
Keep: wallet locking, frozen reservation prices, retries, ownership/device limits,
historical checks and results. Legacy unspecified-service API remains paid.

Acceptance:
- Only admin/browser can create/list codes; normalized code is unique.
- Counts include zero, reject negative/fractional/unknown-service input.
- Redeem atomically at registration or wallet; duplicate never credits twice.
- Matching-service quota is reserved once, settled once, refunded on release.
- Exhausted/nonmatching credits fall back to money; recompute remains paid.
- Scan quote counts the available quotas and the UI explains free/paid portions.
- CSV help documents supported UTF-8 formats, example and usable template;
  hover, keyboard and touch can open it.

Implementation: immutable codes, per-service balances and unique account/code
redemptions. Wallet locking serializes redemption, reservation and refund.
Free checks are reserved at run creation, so a concurrent run cannot increase the
quoted paid portion; stale credit fingerprints return409. Shared completion refunds
only unused credits and refreshes a preloaded Check after taking the wallet lock.
Legacy unspecified-service checks retain paid prices; recompute is unchanged.
CSV help uses the existing popover inside the native dialog, with UTF-8/BOM template,
semicolon/comma/TSV guidance, quote escaping, keyboard/click and hover support.

Evidence (disposable SQLite/PostgreSQL and fake providers):
- Final server suite:277 passed; includes PostgreSQL simultaneous redemption,
  last-credit reservation and refund, stale quote/cancellation, recompute and
  fresh/legacy/current-to-head migration preservation.
- Preloaded-Check PostgreSQL regression failed before the completion fix
  (remaining2 instead of1), then passed. Production stream stop regression covers
  a free settled check, one refunded credit and one120-kopeck paid check.
- Frontend:85 passed; lint passes with existing warnings; TypeScript/Vite build passes.
- Existing agent scan/billing/recovery/screenshot scope:52 passed.
- Browser1280x900 and390x844: admin create/duplicate, wallet invalid/valid/repeat,
  registration invalid/valid, quote free portion, malformed CSV/example/groups/save,
  popover click/Enter/Escape. Final console empty; mobile dialog has no horizontal
  overflow. Hover is configured in the component; pointer-only hover was not exercised.
- Template download name/href/BOM and parser verified; browser download-event capture
  timed out, so OS download completion is unverified.
- Independent Astra planner and Sol/Astra final reviews completed. Astra found the
  double-refund race above; after the fix no further blockers. Requested Terra builder
  was unavailable; the main agent implemented the change.
- Logs/screenshots: C:/codex-tmp/airate-promos-20261014/ (not committed).

Deployed with report changes through PR58; production CI38532175701 attempt2
passed on b3c1f3055e9a52dab8a216be7f0ee046742a6c91. Migration20261014_promo_codes
preserved all 26 existing tables/columns, verified on a restored copy and live
before worker restart. Compatible rollback 0274ab3 includes credits/refunds and
passed copied-DB readiness. Public readiness/assets and pricing120 verified.
Remaining: no live paid provider/payment checks; backups remain on this VPS.
No expiration, global use limit or editing existing codes added.
