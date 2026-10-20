# Approved AIRate hero

Approved desktop and mobile previews were implemented from production base
`08053d4fcd4aa26d95952c2adb8ba23b44ff06a8`. The existing public header and all
subsequent homepage sections remain. The hero has one «Попробовать →» link to
the configured cabinet URL.

Source: [Figma frame 3:7](https://www.figma.com/design/4fbUajD5Q22TAeal3vHfbc?node-id=3-7).
The approved v13 exports are in `frontend/src/assets/landing/`. Original SVG
card details, gradients, logos and sparkles are embedded in the Lottie JSON.
The desktop background is the original Figma SVG. Narrow or portrait screens use
source-color radial gradients without texture. Portrait viewports use the tall
composition; landscape viewports use the wide one. The existing header is more
compact on the landing page only. Its measured height is subtracted from 100svh,
so the header and hero together fill the viewport with browser controls expanded.
This stable height prevents artwork rescaling as mobile browser bars hide/reappear
during scrolling; actual window resizing and rotation still adapt the layout.
Artwork fits the remaining space without cropping.

Both 60fps compositions loop in 12 seconds. Scanners finish before data reaches
the report; checks accumulate to 3, 9 and 12 of 15 square cells. Percentages,
bars and five full-width chart lines reset smoothly to their initial state.
Chart stroke width is 0.75 units. Check positions are shuffled in the approved
export and repeat with that export.

The player loads only the selected composition. Preference/viewport changes and
unmount abort stale loads and destroy the old player. The visible pause button
was removed at the user's request; hidden documents still pause. Reduced motion and loading failure retain
a lightweight transparent WebP of the exported first frame (33–36KB).
Versioned public fallback URLs are identical in prerendered and hydrated markup.

Validation: 125 frontend tests, lint (existing warnings plus a fast-refresh
export warning), production build, independent review, and disposable browser
checks of desktop/mobile, reduced motion and failed animation loading. The
viewport-height adjustment also checks phones, tablets, desktop and short landscape
windows: hero bottom equals viewport height, without horizontal overflow or a
visible pause control. Existing lifecycle tests and the production build pass.
CI retains backend, PostgreSQL, image, backup/isolated restore, migration-head,
readiness and rollback gates. No backend or migration changes are included.

Real-device Safari/Android rendering remains unverified.
