# AI Mentions product interface

Current visual direction: the supplied 2026-10-12 prototype, navy #153d75,
blue #236ac6, orange #f25c37, white panels on #f5f7fa and subtle neutral borders.
Keep the marketing landing separate from the operational cabinet.

Source of truth for cabinet chrome and tokens: `frontend/src/prototype.css`.
Static layout reference: `mockups/dashboard.html`. Brand mark file: `assets/airate.ico`.
Do not invent a parallel palette; refine in place.

Use the prototype sidebar for Overview, Projects, Queries, Sources, Settings,
Schedule, Runs, Account and Help. Prefer aligned rows,
tables and grouped forms over a grid of decorative cards. Keep headings 24–32 px, body
14–16 px, readable control labels, 44 px primary control heights, 8/16/24 px spacing.

Use Lucide icons with text labels, solid primary buttons, restrained keyboard focus and semantic
success/warning/error text. Do not rely on color alone. On narrow screens collapse navigation
into a labelled horizontal list, stack forms and contain table scrolling locally.
Pointer clicks must not add bright outlines or focus glows. Keep keyboard focus visible
with a subtle background or border change; calendar controls share one spacing and type style.
Cabinet dropdowns use the shared AppChoice menu and option styling. Compact toolbar
buttons and dropdown triggers have 9 px corners and the same 36 px height, including
icon-only actions; align their edges within each row.

Reduce animation to 150–200 ms state transitions and respect prefers-reduced-motion.
Always show pending, error, offline and empty states. Avoid replacing a populated form
while polling status. Retain existing readable typography and account/payment flows.
