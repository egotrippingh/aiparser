# Answer display renderer

## Outcome

Render captured Markdown reference citations as normal safe links and remove synthetic
answer-source tiles, without changing server captures or storage.

## Scope

Frontend answer content/evidence components, result dialogs, tests and generated `web/`.
Preserve product cards, brand highlighting, safe-link policy and XML organization snippets.

## Acceptance

- Reference definitions resolve in prose, headings, lists, tables and bold text; code stays literal.
- Unsafe or malformed targets remain text.
- Markdown source-card tiles disappear; XML organization text remains ordinary content.
- Source footers omit URLs already rendered and hide when empty.
- Focused and full frontend test, lint and build pass.

## Evidence

Focused regressions reproduced the old source-card tiles and reference/footer defects.
Final checks: 29 focused and 83 full frontend tests passed; lint (existing warnings),
build, diff check and Graphify AST update passed. Browser checks with disposable
accounts confirmed the supplied citation example in project and admin views:
two inline links, no synthetic cards, and only the metadata-only third source in
the footer. Desktop and 390px layouts were inspected without horizontal overflow.

## Next action

Complete independent review, publish this renderer PR into the feature branch and
merge the combined production PR after CI. Migration/rollback gates belong to
the news/provider-pause release; this renderer changes no captures or database data.
