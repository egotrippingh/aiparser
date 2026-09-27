# AIRvision.ru brand assets

## Website integration

- `frontend/public/assets/brand/airvision-icon-graphite.png`: selected transparent PNG logo, recolored with the built-in image generation tool to match the website. Sand frame and branches, graphite interior and check, ivory quotation marks. The original orange asset is retained as a source only.
- `frontend/src/brand.tsx` and `brand.css`: horizontal lockup matching the upper-right reference. Uses the icon plus native text for crisp lettering at small header sizes. The generated raster wordmark was a discarded draft and is not used.
- `frontend/src/brand-theme.css`: shared graphite, ivory and muted orange color tokens for the landing page and cabinet.
- `frontend/src/product-principles.tsx`: five accessible feature tabs and schematic illustrations. Example data is labelled.

The visual direction follows the user's Zen Browser reference (https://zen-browser.app/). No Zen artwork or code was copied.

## Original icon prompt (built-in imagegen)

Extract and faithfully clean up ONLY the upper-left logo icon in the attached four-panel reference, as one isolated production website logo asset. Preserve its exact design: vivid vermilion orange browser window with rounded corners and three white small circles in its top bar, white interior, two black opening quotation marks, orange connecting branches with two orange endpoint circles, orange central circular badge below with a white check. Do not redesign, no text or lettering anywhere, no other panels, no shadows, no paper texture. Flat crisp vector-like edges. Transparent background outside the icon, white interior retained exactly like upper-left. The complete single icon must nearly fill a square canvas with only 4 percent transparent safety margin, no cropping of the lower check badge. Output PNG with real alpha transparency, suitable for a website header logo and favicon.

## Copy constraints

Browser automation collects answers from the services' web interfaces. The primary model analyzes the evidence; the arbiter resolves disagreements with exact-match rules. AI analysis itself uses the server's model API. The landing page does not assert unverified market primacy, perfect accuracy, an invented support SLA, or continuous back-and-forth between models.

## Icon system

### Final recoloring prompt (built-in imagegen)

Edit target: attached AIRvision website logo. Recolor and clean this exact icon to match a calm graphite, warm ivory and sand website. Preserve the rounded browser frame, three header dots, two opening quotation marks, two branching nodes and central check badge, proportions and layout. Replace vivid orange everywhere with flat muted sand #e9ad7c. Replace white inner window with solid graphite #1e1f1c. Make the two quotation marks warm ivory #e5e5d8. Make the three header dots graphite #1e1f1c, check mark graphite #1e1f1c, and thin separating ring around badge graphite #1e1f1c. Exterior must be genuinely transparent alpha, no background panel. Flat solid colors, sharp smooth vector-like contours, absolutely no texture, gradients, shadows or glow. Clean stray pixels from original. No text. One icon nearly fills square canvas with only small safe margins, no clipping. This is a production header icon also used at 32px as favicon; prioritize crisp simplified edges and high contrast.

Website UI icons use the existing Lucide outline family, with a consistent 1.75 stroke. Shared `--air-icon`, `--air-icon-accent` and `--air-icon-surface` tokens control neutral, selected and decorative states. Control icons inherit button contrast; success and error indicators retain their semantic colors. Chart SVGs are unaffected.
