# Public search pages

The homepage and eight public help articles are indexable. The build extends the
homepage sitemap from `frontend/public/` with canonical article URLs from
`frontend/src/help-content.ts`. It omits invented modification dates, priorities
and change frequencies. `/help/` is an alias of the quick-start guide and uses
that guide's canonical URL rather than adding a duplicate sitemap entry.

- `frontend/index.html`: Russian title/description, canonical, Open Graph,
  Twitter summary card and factual WebSite JSON-LD. The verification tag is retained.
- `frontend/public/robots.txt` and `sitemap.xml`: copied into `web/` by Vite and
  served by explicit public FastAPI routes with correct content types, GET/HEAD
  support and revalidation. JS, CSS, service icons and social images remain crawlable.
- Cabinet and legal pages use `noindex, follow` in HTML and `X-Robots-Tag`.
  Robots allows crawling those pages so crawlers can read the exclusion.
- API/schema documentation is disallowed in robots. Unknown pages keep real 404s.
  Caddy already redirects HTTP and the www hostname to the HTTPS canonical host.
- The homepage is rendered from the existing React component during `vite build`,
  then hydrated in the browser. No runtime SSR server or duplicate landing copy is
  needed. Animation starts after hydration and respects reduced motion.
- Help pages use Fumadocs on the existing Vite build. Full article text, navigation,
  support contact and escaped per-page title/description/canonical/Open Graph tags
  ship in HTML before JavaScript runs. React hydrates the same component. The
  server admits only known help slugs; unknown paths return 404. Static search
  indexes paragraphs, steps and CSV examples, with no search backend.
- The social card is a 1200×630 PNG using the existing AIRate logo and palette.

Checks: `npm --prefix frontend test`, `npm --prefix frontend run lint`,
`npm --prefix frontend run build` and `python -m pytest server/test_seo.py -q`.
The HTTP tests also check the shipped homepage text, metadata, sitemap parsing,
robots policy, real social image dimensions, utility exclusions and 404 responses.
Browser smoke uses disposable guest/account responses at desktop/mobile sizes;
it checks hydration, navigation, search, header states and section links. HTTP
checks establish that the complete article content exists without JavaScript.

Help wording follows product tasks and observed Russian search intent: brand
monitoring in neural networks, brand visibility, ChatGPT mentions, prompts,
AI-answer sources and CSV imports. Research on 2026-10-16 used public search
results and primary product pages ([Glasarity](https://glasarity.com/),
[AIMonitor](https://aimonitor.pro/), [Oqra](https://oqra.ai/)) for terminology only.
No connected Keys.so account/token or keyword-volume provider was available;
search frequency is unmeasured and no high-frequency claims are made. The
[Keys.so API](https://apidoc.keys.so/) requires an eligible account and token.
Keep the instructions factual and concise; don't repeat phrases to hit a density.

After deployment, check `/`, `/robots.txt`, `/sitemap.xml`, the social PNG,
utility-page exclusions and the exact release via `/api/v1/ready`. Detailed release
evidence belongs in the delivery PR. Search Console and Yandex Webmaster ownership,
sitemap submission and actual indexing require access to those accounts; a live
200 response does not establish that a URL has been indexed.

References: [Google developer SEO guide](https://developers.google.com/search/docs/fundamentals/get-started-developers),
[Google JavaScript SEO](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics),
[Yandex robots instructions](https://yandex.ru/support/webmaster/en/controlling-robot/robots-txt),
[Yandex sitemap instructions](https://yandex.ru/support/webmaster/en/controlling-robot/sitemap).
