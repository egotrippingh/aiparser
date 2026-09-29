# Landing cleanup and agent presentation

## Scope and acceptance

Remove the landing labels explicitly pictured by the user, along with decorative step/tab numbers and corresponding empty grid tracks. Keep the actual headings, sections and demo counts. Replace the service text pills with four local 30x30 SVGs, retaining alt/title names. Strongest objection: fewer section orientation labels; headings and navigation remain.

Agent: always show Connections and autostart; manual launches show a window regardless of saved account. Only explicit --background with a token starts hidden. First successful login keeps the window visible. Close X continues to hide in tray; tray Quit exits. Strongest objection: longer window; existing scrolling handles this. Confirmed extra defect: initial state-request error hidden behind state-loading branch. Show it and clear only polling errors on successful recovery, preserving action errors.

Check absent/pending/failed browser setup, login failure/recovery, saved and absent token, startup flag, small window scrolling, and scan-active disabled actions. Do not change stored sessions, browser profiles, scans or autostart registration. Use existing frontend checks and desktop-login tests, isolated loopback presentation scenarios, independent review, packaged self-test and browser install probe. Native window/tray interaction is separately recorded as unverified if tooling cannot control it.

## Logo sources

ChatGPT (OpenAI mark) and Google: Iconify logos collection, https://api.iconify.design/logos.json?icons=openai-icon,google-icon . Perplexity: Simple Icons through https://api.iconify.design/simple-icons.json?icons=perplexity . Alice: Yandex asset https://yastatic.net/s3/lpc/8652d32a-b1e9-47f8-821e-bd36acc938d0.svg . Assets are served locally, with no runtime third-party requests.

## Verification

2026-09-29: Sol/Astra independent review cleared fixes after correcting obsolete login copy. Final frontend checks `build/qa/frontend-final-20260929-03/report.json` pass (26 Vitest checks, lint, build, fixture syntax); desktop login tests: 3 passed. Main browser: landing four loaded logos measured 30x30, no removed label selectors, no desktop overflow, arrow-key tab navigation and FAQ opening passed. Agent fixture: initial 503 error visible, successful polling clears it, settings/service login actions visible without a toggle. QA fixture never uses native agent or real auth data.

Unverified: native WebView2 X/tray/Windows logon and minimum-size window interactions; real native confirmation UI; 390px viewport override had no measurable effect in IAB. Packaged self-test/browser probe and deployment evidence recorded in PROJECT_STATE.md after release.
