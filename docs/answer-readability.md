# Readable answers

The database keeps the captured answer text for display.  New provider captures
also keep `extra.plain_text`: rules, LLM review, and arbitration use that exact
plain capture, so anchor labels and URLs do not affect matching.

`app.scanner.adapters.readable.SERIALIZE_JS` reads only the selected live DOM
subtree.  It emits paragraphs, headings, lists, code and safe HTTP(S) anchors;
controls and hidden elements are excluded.  It never edits provider DOM.

Older ChatGPT rows can contain one confirmed leading map block.  The frontend
removes it only when it starts with a rating, contains the exact map gesture
line, ends at `Оставить отзыв`, and is followed by prose.  The untouched text
remains available in `Исходный текст`.

## Verification

- `python -m pytest tests/test_readable_capture.py tests/test_scan_plan.py -q`
  checks all four capture paths and unchanged rules/primary/arbiter input.
- `cd frontend && npm test && npm run lint && npm run build` checks safe links,
  mixed/nested lists, headings, literal code and legacy map cleanup.
- The synthetic DOM in `tests/fixtures/answer-readable.html` covers all four
  services, absent/unsafe href, empty Alice footnotes, multiline anchor labels,
  and nested code whitespace. Evaluate `SERIALIZE_JS` on each article using the
  matching mode in a disposable browser page; compare plain Alice/Google parts
  with the previous splitter, then render the emitted display text.
- On the disposable report page, open the saved map example: prose starts after
  the map, its original is available in the disclosure, and the saved bare-domain
  source links to its actual URL. At 360px, text and sources stay within the panel.

Old captures lost anchor-to-label relationships: only an unambiguous domain/path
can reuse a saved source; other source URLs remain in the source list. Live
provider sessions and Windows interactive update are not exercised by these checks.
