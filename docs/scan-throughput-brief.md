# Scan throughput follow-up

The follow-up keeps one browser request per provider and the published
durable-capture boundary. It must not create accounts, proxies, or background
infrastructure.

## First stage acceptance

- A newly captured answer gets the normal server analysis budget: two primary
  and two arbiter attempts for the lifetime of its check ID.
- An explicit continuation of a saved answer may use at most four attempts per
  primary/arbiter cache. Re-reserving the same check cannot reset either
  counter.
- After the saved retry budget is exhausted, the operator can abandon the raw
  answer. The raw payload remains with state `abandoned`, an error result is
  recorded, the existing release endpoint receives the check ID, and the scan
  can finish. Cached primary analysis settles once; absent primary analysis
  releases the reservation.
- Browser/password/device-code token replacement is serialized with scan
  admission; an active scan keeps its pinned bearer.
- ChatGPT and Perplexity treat a generation-settling timeout as an adapter
  error, never as a completed answer.

## Ordered follow-up

After the first stage, production defaults add metadata-only capture
enumeration, phase timings, one durable screenshot-outbox consumer, and a
shared request-specific HTTP client lifecycle. Each needs deterministic checks
and measured before/after evidence. Two analysis workers, direct form filling,
scroll changes, and Google readiness changes remain frozen opt-in experiments
until provider measurements show a benefit. Existing provider floors and
legacy snapshots remain unchanged.

## Measurement and experiments

- Default scans use one analyzer. The frozen two-analyzer experiment is selected
  in a local developer build before starting a scan with `PUT /api/settings`
  body `{"analysis_workers":"2"}`. Configured desktop agents intentionally
  reject that settings route; this is not a client-facing switch. `"1"` is the default and is recorded in the
  immutable scan snapshot. The bounded queue remains two captures, failed
  workers stop admission and retain raw captures for an explicit continuation.
- Controller events/logs record ephemeral `browser_capture`,
  `wait_for_analyzer`, `analysis`, `settlement`, and `analysis_stage` timings.
  `analysis_stage` and the historical result duration begin after a durable
  capture is dequeued; they are not end-to-end scan totals. Screenshot uploads
  log their own duration because they run in the separate durable worker.
- No provider experiment changes shipped adapters. Run the deterministic harness
  first: `python scripts/benchmark_scans.py --self-check`. A copied-profile live
  candidate requires all explicit flags, for example:
  `python scripts/benchmark_scans.py --output <fresh-dir> --services alice google_aio --variant candidate --direct-fill --skip-scroll --google-dom-ready`.
  It checks exact Unicode/multiline field content, retains screenshot stitching,
  waits Google DOM navigation plus its existing captcha/consent/overview and
  full-text quiet rules, and writes only sanitized progress hashes.
