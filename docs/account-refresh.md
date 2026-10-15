# Account entry and balance top-up

The approved account design uses the production AIRate logo, Onest, light neutral
surfaces and navy actions. Public entry is a single compact form. Yandex has one
common entry for login and registration; account selection and safe linking remain
the server's existing responsibility.

Email confirmation keeps credentials only in React memory. Reload restores the
existing email proof and asks for the password again. Returning through login or
editing a password must also reveal missing or mismatched credentials. Optional
registration promo entry stays editable during confirmation.

Balance top-up uses the existing payment API, integer kopeks and server-supplied
method availability and limits. The capacity estimate uses the current check price;
ordinary admin checks remain free. Administrators still see their real money and
reserved funds because saved-answer recompute can be paid. Payment history, pending
continuation, reconciliation, free allocations and password/Yandex settings remain.

Method icons use the existing Lucide library. User-facing text names the payment
service generically and warns about possible commission before redirecting. No
new provider, dependency, schema, account-linking or billing behavior is introduced.

## Design references

- [Untitled UI login patterns](https://www.untitledui.com/components/log-in-pages),
  Jordan Hughes: compact entry form, provider separation and field hierarchy.
- [Untitled UI billing settings](https://pkg.untitledui.com/react/components/settings-pages/settings-14):
  labelled payment details and restrained history layout.
- [Yandex ID button design](https://yandex.ru/dev/id/doc/ru/codes/buttons-design):
  vector mark from the public example. The common continuation wording follows
  the approved AIRate design.

This is an HTML/CSS adaptation of public patterns; paid kit source is not included.

## Release checks

Run frontend tests, lint and build. Focused coverage includes registration credential
recovery, admin paid-recompute balance disclosure, money parsing and provider-neutral
top-up markup. Existing server suites cover email registration, Yandex, password
recovery, payments and promo accounting.

Browser smoke uses the disposable frontend fixture, with mocked email/OAuth/payment
responses and an isolated database. Verify code/promo rejection, reload/back recovery,
password reset, read-only Yandex email, decimal amount and method limits, invoice
failure/retry, unavailable options, checkout return and pending continuation. Verify
desktop, 800px tablet and 390px mobile layout. Do not create a real payment to test
presentation. Detailed evidence belongs in the release PR and ignored local run logs.

Publish through the existing [delivery gates](../deploy/DELIVERY.md), retaining
backup restoration, schema-head equality, rollback and exact-revision readiness.
