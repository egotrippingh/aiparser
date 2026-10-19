# Approved AIRate hero

Approved desktop and mobile previews were implemented from production base
`08053d4fcd4aa26d95952c2adb8ba23b44ff06a8`. The existing public header and all
subsequent homepage sections remain. The hero has one «Попробовать →» link to
the configured cabinet URL.

Source: [Figma frame 3:7](https://www.figma.com/design/4fbUajD5Q22TAeal3vHfbc?node-id=3-7).
The approved v13 exports are in `frontend/src/assets/landing/`. Original SVG
card details, gradients, logos and sparkles are embedded in the Lottie JSON.
The desktop background is the original Figma SVG. At up to 680px, the mobile
composition replaces it with source-color radial gradients without texture.
Mobile artwork is capped at 480px wide for larger narrow screens.

Both 60fps compositions loop in 12 seconds. Scanners finish before data reaches
the report; checks accumulate to 3, 9 and 12 of 15 square cells. Percentages,
bars and five full-width chart lines reset smoothly to their initial state.
Chart stroke width is 0.75 units. Check positions are shuffled in the approved
export and repeat with that export.

The player loads only the selected composition. Preference/viewport changes and
unmount abort stale loads and destroy the old player. Pause supports keyboard
activation; hidden documents pause. Reduced motion and loading failure retain
a lightweight transparent WebP of the exported first frame (33–36KB).
Versioned public fallback URLs are identical in prerendered and hydrated markup.

Validation: 125 frontend tests, lint (existing warnings plus a fast-refresh
export warning), production build, independent review, and disposable browser
checks of desktop/mobile, pause, reduced motion and failed animation loading.
CI retains backend, PostgreSQL, image, backup/isolated restore, migration-head,
readiness and rollback gates. No backend or migration changes are included.

Real-device Safari/Android rendering remains unverified.
