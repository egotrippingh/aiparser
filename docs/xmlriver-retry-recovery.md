# Recover Yandex AI answers after transient XMLRiver failures

Base: production `c21633d347f922f4da4ded5e0d23764b8589636d`.

## Problem and scope

API500 already receives bounded retries. Some Yandex XML responses repeatedly
contain an empty AI content element. The documented `raw=page` mode returned an
actual Yandex page with nonempty AI prose inside `section.FuturisGPTMessage` and
`FuturisMarkdown`, while keeping the same query, geography, engine and `ai=1`.
Add this fallback inside the existing six-request budget and durable collector.
Keep pricing, billing, owner scope, saved results and stop semantics intact.

## Acceptance

- XML first success/confirmed absence behaves as before; Google is unchanged.
- Yandex transient API500/incomplete AI may retry through the original page.
- Only known AI-container prose/cards count; ordinary SERP, captcha, empty or
  malformed raw responses never become a successful answer or confirmed absence.
- All paths share the same request budget, cancellation checks and diagnostics.
- Existing provider save/token fencing and worker analysis settle a real recovered
  answer once, without replacing earlier results or changing their charges.
- PR, independent correctness/risk review and existing delivery gates pass.

## Recovery evidence

One user-authorized raw-page request returned558585 bytes at21:55 MSK. Its source
SHA-256 is `0021a5fa1ab24bdb351d5408dfa1915fc2342b599ac533c080d9c01eeaaad554`.
The private source stays outside Git at
`/opt/airate/releases/xmlriver-recovery-20261022/response.html` on the server.
The existing69 results must remain unchanged. Recovery must validate the fixed
run/task/owner/reserved check under the same transaction locks used for save;
then ordinary worker analysis must produce one final result and terminal70/70.

Implementation, checks, review, release and terminal live evidence are pending.

## Prepared checks

- Targeted provider/parser checks: 74 passed; four new diagnostic checks passed.
- Disposable operator checks: five passed (single save, stopped run, released check,
  active task and changed snapshot). The operator stays outside Git and validates
  source hash, frozen request and original reservation before the ordinary save.
- Independent correctness review found no release blocker. Raw XHTML starting with
  an XML declaration remains an unobserved unsupported fallback edge.
- Risk review, browser compatibility subset, CI and live completion remain pending.

Browser compatibility subset: 7 passed (32 deselected); AST-only graph refresh passed.
