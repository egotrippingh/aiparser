# Registration email confirmation

Password registration requires a six-digit code delivered through the existing
TLS SMTP configuration. No account, wallet, promo credit or session is created
until confirmation succeeds. Existing accounts keep their current access.

`POST /api/v1/auth/registration/code` accepts `{email}` and returns a private
`ticket`, `expires_in: 600` and `resend_after: 60`. The cabinet retains the ticket
in tab session storage across reloads; passwords and codes are not persisted.
`POST /api/v1/auth/register` accepts the existing credentials/promo/connect fields
plus `ticket` and `code`. The ticket is bound to the normalized email.

Codes expire after ten minutes and reject further confirmation after five wrong
attempts. A successful registration consumes its ticket atomically with account,
wallet, promo, optional device connection and session creation. Failed promo or
connection validation rolls everything back. Previous tickets remain valid until
expiry when another code is requested; email uniqueness prevents duplicate accounts.
The database stores hashes of tickets and ticket-bound codes, never raw codes.

Sending is limited to one request per email per minute, three per email and twenty
per source IP per fifteen minutes. PostgreSQL transaction advisory locks reserve
both budgets before SMTP, including requests for existing accounts. SMTP failure
returns an error and retains the cooldown reservation. SMTP absence fails closed.
Expired challenges are removed on a later code request. The HTML/plain text email
uses the approved template with a centered code, embedded logo and automated footer.

Yandex registration remains a separate OAuth/PKCE flow: a new provider identity
receives a one-use registration ticket and creates an account after choosing a
password. A known identity signs into its account. A matching email without a
linked identity requires explicit linking after password login. Provider email is
read from [the Yandex ID profile](https://yandex.ru/dev/id/doc/ru/user-information).

Migration `20261015_email_registration` adds only `email_registrations`; it does
not modify old accounts or mark them unverified. The ordinary migration-head
deployment gate remains enabled. Before live activation, restore a fresh backup,
verify preservation of existing tables and rehearse candidate/fallback readiness.
A compatible fallback must also reject ordinary registration rather than restore
the old registration endpoint without email proof. Never downgrade or restore
over the live database to roll back this additive schema.
