# Account recovery and promo controls

Outcome: Yandex registration completes only after a password is saved; existing
OAuth accounts can set a password. Admins control promo availability, expiry and
total distinct-account redemptions. Recovery uses the account email for both
registration methods; SMTP will be supplied later.
Base: clean codex/promo-codes,3113062; production b3c1f30.
Branch: codex/account-promo-controls.

Keep: existing Yandex sign-in, explicit identity linking, cookie/Origin and device
boundaries, immutable promo scan counts, issued credits, paid recompute, feedback20.
New OAuth registrations remain separate pending records until password completion;
no usable session or device approval is issued before that transaction succeeds.
Promo restrictions affect new redemptions only; replay is idempotent after expiry.
Limit counts distinct accounts globally, serialized under the promo row lock.
Admin edits use revision conflicts. No user data or credentials in test fixtures.

Acceptance:
- Fake OAuth: password required, weak password/expiry/replay rejected, completion
  creates one account and optional promo atomically; existing accounts still enter.
- Password settings: current password required when already set; device and foreign
  Origin rejected; reset works for email and Yandex accounts with FakeMailer.
- Promo: admin-only edit, toggle/expiry/exhaustion reject new grants, old credits
  retained; PostgreSQL concurrent distinct accounts cannot exceed the last slot.
- Additive migration preserves prior users, wallets, codes, grants and checks.
- UI smoke: registration, password settings, recovery availability and promo edits,
  success/error, desktop/narrow, keyboard and console; generated web assets included.
- Full server suite with disposable PostgreSQL, frontend test/lint/build, diff check.

Steps: backend and regression tests; UI and fake browser; independent Sol/Astra
review; fix findings, authorized delivery with backup/restore/schema admission.
SMTP delivery remains unavailable until the sender configuration is supplied.
Evidence (reviewed source tree, 14 October 2026):
- Full server suite with disposable PostgreSQL: 295 passed; added deterministic
  PostgreSQL browser-exchange/reset regression separately: 1 passed.
- Frontend: 87 passed; lint passed with existing warnings; production build passed.
- Five auth regressions failed before their fixes; ticket validation and revocation
  passed afterward. Login/ticket issuance now serialize with reset under User lock.
- Independent Sol high and Astra high reviews: no remaining blockers. Astra also
  verified overlapping browser exchange/reset on its own PostgreSQL schema.
- Fake browser: required Yandex password/confirmation and promo rejection/grant,
  password settings, promo condition persistence/date keyboard entry, mobile390
  without page overflow, desktop1440, no-mail disabled submit and honest notice;
  test-mail request worked, admin console error/warn log empty. No real email sent.
- Additive migration/metadata checks preserve old accounts, balances and grants.
Release: production remains b3c1f30 / 20261014_promo_codes. Deployment is held while
the user's unfinished cloud scan pauses/retries; no live migration or restart.
Next: verify exact PR SHA/CI, confirm the scan has completed, prepare a compatible
fallback for 20261014_account_promos, then isolated restore/upgrade/preservation
and the authorized live migration under the release lock before production merge.
