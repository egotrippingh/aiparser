# Project feedback and scan review

Prepared 2026-10-08; not published or verified against live provider answers.

The report answer dialog accepts `correct`, `false_positive` and `missed` labels,
an optional 400-character explanation, and removal. Original answers, statuses,
charges and report statistics remain unchanged. Only the project owner can label
its results; browser sessions are required. Failed or empty answers cannot become
training examples. Old results from a different brand cannot be relabelled for
the new brand.

This is inference adaptation through examples, not fine-tuning model weights.
Each project stores at most 20 labels in its existing configuration; only the
six latest corrections matching the current brand/aliases/domains are used.
Examples contain bounded excerpts (1800 characters of answer, 500 of prompt and
quote, up to five 300-character source URLs). Long-answer evidence can be outside
the excerpt: the owner should explain the identity distinction in the comment.
Full original answers remain available separately in existing result storage.
`correct` labels are retained for review and do not force semantic analysis.

Creating a managed run freezes its examples. A short clarification marker asks
the existing capable agent to use semantic analysis even after a rule hit. The
server injects complete bounded examples into primary and arbiter requests,
avoiding the agent's 2000-character clarification cap. The existing clarification
path allows a negative semantic verdict to override rules and disables remote
source-page promotion. It reports failed required analysis as an error. Devices
without clarification support must be updated before starting an adapted run.
Removing a label affects future runs, not in-flight or saved pending work.
Examples are scoped to one project, and changing brand identity deactivates old
examples. Prompts explicitly treat examples/comments as data, reject generic
role/service descriptions as brand proof, and evaluate the new answer independently.
These restrictions do not establish a measured improvement in model accuracy.

Feedback and editor saves use the same project revision CAS. A stale overlapping
write returns 409 rather than overwriting a newer configuration. Editor saves
preserve the server-owned labels; user-provided configuration cannot populate them.
No schema migration, billing changes, Windows agent code or release is required.

Administrators have a separate paginated scan journal searchable by email,
project, brand and query. Detail shows the original answer, source links, mention
types, evidence quote, owner label and persisted primary/arbiter reasoning/model.
Screenshot URLs require an admin browser session and resolve through the result
owner's Check, even when another account has the same client check ID. The
existing 90-day screenshot availability policy applies. Private responses use
`Cache-Control: no-store`; no answer payloads are added to process logs.

## Validation

- Full server run at initial implementation: 78 passed. Final affected feedback
  suite: six passed; representative generic-design-role regression and existing
  rule/model tests: 24 passed. The extra regression was added after the six-test run.
- Cases include owner/admin/device boundaries, brand changes, bounded examples,
  editor preservation, deterministic overlapping feedback writes, stale editor
  rejection, frozen run context through real analyze/arbitrate endpoints, foreign
  device rejection, same-check-ID account isolation, and expired screenshots.
- Frontend: 50 existing tests passed; lint passed with existing warnings; final
  production build passed. A disposable local database and headless Edge exercised
  admin brand search/full answers, absence of admin navigation for an ordinary
  owner, saving/removing feedback, and desktop/mobile viewports without page errors.
- Independent correctness and authorization reviews completed; screenshot access,
  brand search, label copy and screenshot-response race findings were corrected.
- `git diff --check` passed. `graphify update .` rebuilt the ignored code graph
  without model calls (aggregated visualization for the graph above 5000 nodes).

Live S3/provider checks, PostgreSQL concurrency and measured before/after model
accuracy remain unverified. The supplied Neighbours Expert screenshot shows generic
design roles rather than identifiable brand evidence in the visible answer/links;
the saved analysis/arbiter records are still needed to establish its original cause.

Delivery follows [DELIVERY.md](../deploy/DELIVERY.md): PR into `production`, CI,
backup/isolated restore, readiness and application rollback. Existing production
data is preserved; no historical statuses are automatically rewritten.
