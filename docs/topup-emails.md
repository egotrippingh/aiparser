# Balance top-up email

Real Coinso credits queue one notification per payment order in `topup_emails`.
The order credit, wallet balance, ledger entry and notification are committed
together. The existing verified invoice checks and wallet/order locking stay in
place. Test payments, invalid confirmations and older already-paid orders do not
create mail. Refunds and manual administrative credits are outside this feature.

The snapshot contains the account email, credited integer kopeks and balance
immediately after the credit. A delayed message labels that balance accordingly.
The email is a transaction notification, not a fiscal receipt. The HTML follows
the approved account email drafts; its current orange brand mark is an inline
PNG attachment, so it requires no remote image request or SVG support. Plain text
is included as the alternative. No open or link tracking is added.

## SMTP activation

The worker uses the same `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_SECURITY` and `PUBLIC_BASE_URL` as account recovery.
Use `connect.smtp.bz`, port `2525`, `starttls`, and the existing private SMTP
credentials. Keep all secrets in `/opt/airate/deploy/.env` with mode 0600.

Without SMTP configuration, credits still queue mail with zero attempts.
Once the reviewed release and migration are installed and verified SMTP settings
are enabled, the lifespan worker picks up pending mail automatically, one message
per 15-second tick. A known SMTP refusal (including domain moderation) retries
with a delay from one minute up to one hour. A disabled/misconfigured provider
does not reverse or delay the credit. Domain approval alone does not install this
release or enable environment settings; after approval first verify the approved
test address and activate SMTP, then verify readiness and password recovery.

## Delivery states and ambiguous acceptance

- `pending`: waiting for configuration, a retry deadline, or the next worker tick.
- `sending`: a committed claim; another worker cannot claim it. A stopped process
  may leave this state behind even if SMTP accepted the message.
- `sent`: SMTP accepted the message; this does not prove inbox delivery.
- `uncertain`: a disconnect/timeout during `send_message`, or an unexpected
  delivery exception. The application cannot prove whether SMTP accepted it.

The worker releases its DB session before SMTP. Known negative replies are safe
to retry; a successful DATA reply followed by failed QUIT is still success.
Both `sending` left by a crash/final DB failure and `uncertain` deliberately
require operator inspection instead of automatic resend. `send_message` does
not expose every transport phase, so an early disconnect can conservatively
require inspection too. A stable Message-ID helps correlate provider logs; SMTP
does not promise exactly-once delivery or deduplication.

Inspect private DB/provider logs for an affected order and Message-ID
`<topup.ORDER_ID@airate.tech>`. Do not log recipients, message bodies or secrets.
Useful aggregate monitoring query:

```sql
SELECT status, count(*), min(created_at)
FROM topup_emails GROUP BY status;
```

`min(created_at)` is the age of the oldest queued notification, not a send/claim
timestamp; an old payment may have just started sending after SMTP activation.
Do not infer a stopped worker or safe resend from that timestamp alone.

For stale `sending`, first confirm the owning worker has stopped. Look up the
Message-ID in SMTP.BZ delivery logs. Mark the exact row `sent` only when acceptance
is confirmed. Return that exact row to `pending` with `next_attempt_at` set to now
only when non-acceptance is confirmed. If the provider cannot establish the
outcome, leave it for inspection: a blind reset risks sending a second email.
Never reset all `sending` rows at startup or change payment/ledger/wallet records
to repair mail. Log warnings/errors signal delivery failures without including
SMTP reply bodies; monitor the state counts above as well as application logs.

## Migration and release

`20261015_topup_emails` adds one empty table and its due index. No existing orders
are backfilled and no balances change. Before production rollout follow
[delivery](../deploy/DELIVERY.md): the changed Alembic head intentionally blocks
unattended deployment. Verify backup/isolated restore, preservation of existing
records and a schema-aware fallback image; old images reject a newer schema
head even for this additive migration. Do not bypass the gate or automatically
downgrade a production database to roll back application code.

Deterministic coverage is in `server/test_topup_emails.py`: credit/outbox
atomicity and duplicates, non-credit paths, SMTP retry/ambiguity/QUIT behavior,
post-acceptance DB failure, multipart output, upgrade preservation, and a
PostgreSQL race of payment confirmations plus simultaneous worker claims.
Set `AIRATE_TEST_POSTGRES_URL` to an isolated disposable database for the latter.
