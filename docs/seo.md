# Homepage search metadata

The only search landing page is `https://airate.tech/`. The XML sitemap lists that
canonical URL only. It intentionally omits invented modification dates, priorities
and change frequencies. Add another URL only when it has public, indexable content.

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
- The social card is a 1200×630 PNG using the existing AIRate logo and palette.

Checks: `npm --prefix frontend test`, `npm --prefix frontend run lint`,
`npm --prefix frontend run build` and `python -m pytest server/test_seo.py -q`.
The HTTP tests also check the shipped homepage text, metadata, sitemap parsing,
robots policy, real social image dimensions, utility exclusions and 404 responses.
Browser smoke uses disposable guest responses at desktop/mobile sizes and with
JavaScript disabled; it checks hydration, tabs, FAQ and reduced motion.

After deployment, check `/`, `/robots.txt`, `/sitemap.xml`, the social PNG,
utility-page exclusions and the exact release via `/api/v1/ready`. Detailed release
evidence belongs in the delivery PR. Search Console and Yandex Webmaster ownership,
sitemap submission and actual indexing require access to those accounts; a live
200 response does not establish that a URL has been indexed.

References: [Google developer SEO guide](https://developers.google.com/search/docs/fundamentals/get-started-developers),
[Google JavaScript SEO](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics),
[Yandex robots instructions](https://yandex.ru/support/webmaster/en/controlling-robot/robots-txt),
[Yandex sitemap instructions](https://yandex.ru/support/webmaster/en/controlling-robot/sitemap).
