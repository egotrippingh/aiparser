import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { expect, test, vi } from 'vitest'

const tagUrl = 'https://mc.yandex.ru/metrika/tag.js?id=114026759'

test.each(['index.html', 'cabinet/index.html', 'docs/index.html', 'terms/index.html', 'privacy/index.html'])(
  '%s initializes the supplied Metrika counter asynchronously and includes its fallback', file => {
    const html = readFileSync(new URL(`./${file}`, import.meta.url), 'utf8')
    const scripts = [...html.matchAll(/<script type="text\/javascript">([\s\S]*?)<\/script>/g)]
    expect(scripts).toHaveLength(1)
    expect(html).toContain('https://mc.yandex.ru/watch/114026759')
    for (const alreadyLoaded of [false, true]) {
      const insertBefore = vi.fn()
      const tag = { async: 0, src: '' }
      const document = {
        scripts: alreadyLoaded ? [{ src: tagUrl }] : [],
        createElement: () => tag,
        getElementsByTagName: () => [{ parentNode: { insertBefore } }],
        referrer: 'https://example.invalid/',
      }
      const context = { window: {}, document, location: { href: 'https://airate.tech/' } }
      context.window = context
      runInNewContext(scripts[0][1], context)
      expect(insertBefore).toHaveBeenCalledTimes(alreadyLoaded ? 0 : 1)
      if (!alreadyLoaded) expect(tag).toEqual({ async: 1, src: tagUrl })
      expect(runInNewContext('Array.from(window.ym.a[0])', context)).toEqual([
        114026759, 'init', {
          ssr: true, webvisor: true, clickmap: true, ecommerce: 'dataLayer',
          referrer: document.referrer, url: context.location.href,
          accurateTrackBounce: true, trackLinks: true,
        },
      ])
    }
  },
)
