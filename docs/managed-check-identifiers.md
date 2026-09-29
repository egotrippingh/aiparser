# Managed check identifiers

Managed scans use the control-plane query UUID in every reservation, model call, settlement, screenshot upload, recovery, recheck, and result export. Local integer query IDs remain valid only for unmanaged scans.

Before an outbox flush, the agent atomically repairs a proven older local-ID entry when its scan belongs to the connected account, its snapshot maps the query, and the canonical ID was reserved. Foreign, incomplete, or conflicting entries remain queued unchanged. This does not verify a real device queue or provider response.

Both billing and screenshot uploads exclude known foreign, unmapped managed and conflicting retained work. Interrupted recovery respects the account and existing conclusive queue statuses. Retained ambiguous work requires diagnosis; it is not silently deleted or charged. Server assignment and lease checks remain authoritative.

The regression suite uses disposable SQLite databases and the real server API to verify canonical settlement after an old local-ID failure, one ledger charge after retries, another assignment's reservation, an injected mid-transaction rollback, conflicts, owner isolation and the actual scanner model/arbiter/result ID flow. Desktop fixtures cover a remotely paused run both with and without a local controller.
