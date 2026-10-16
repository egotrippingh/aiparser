import path from 'node:path'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { createServer, defineConfig } from 'vite'

// Собранный интерфейс кладётся в ../web и коммитится: start.bat запускает
// программу без Node. Node нужен только для разработки фронта.
const backend = 'http://127.0.0.1:8756'
const accountBackend = 'http://127.0.0.1:8757'

export default defineConfig({
  plugins: [react(), tailwindcss(), {
    name: 'prerender-public-pages',
    apply: 'build',
    async closeBundle() {
      const server = await createServer({
        configFile: false,
        root: import.meta.dirname,
        mode: 'production',
        plugins: [react()],
        server: { middlewareMode: true },
      })
      try {
        const { renderLandingPage } = await server.ssrLoadModule('/src/landing-render.tsx')
        const { HELP_ARTICLES, helpHref, helpSearchContent } = await server.ssrLoadModule('/src/help-content.ts') as typeof import('./src/help-content.ts')
        const { renderHelpPage, renderHelpHead } = await server.ssrLoadModule('/src/help-render.tsx')
        const file = path.resolve(import.meta.dirname, '../web/index.html')
        const html = await readFile(file, 'utf8')
        if (!html.includes('<div id="root"></div>')) throw new Error('Homepage root placeholder is missing')
        await writeFile(file, html.replace('<div id="root"></div>', () => `<div id="root">${renderLandingPage()}</div>`))
        const helpTemplate = await readFile(path.resolve(import.meta.dirname, '../web/help/index.html'), 'utf8')
        const { createSearchAPI } = await import('fumadocs-core/search/server')
        const api = createSearchAPI('simple', {
          indexes: HELP_ARTICLES.map(article => ({ title: article.title, description: article.summary, url: helpHref(article), content: helpSearchContent(article) })),
        })
        await writeFile(path.resolve(import.meta.dirname, '../web/assets/help-search.json'), await (await api.staticGET()).text())
        for (const article of HELP_ARTICLES) {
          const articleDir = path.resolve(import.meta.dirname, `../web/help/${article.slug}`)
          await mkdir(articleDir, { recursive: true })
          const prerendered = helpTemplate.replace('<title>Помощь AIRate</title>', () => renderHelpHead(article)).replace('<div id="root"></div>', () => `<div id="root">${renderHelpPage(article)}</div>`)
          await writeFile(path.resolve(articleDir, 'index.html'), prerendered)
          if (article === HELP_ARTICLES[0]) await writeFile(path.resolve(import.meta.dirname, '../web/help/index.html'), prerendered)
        }
        const urls = ['/', ...HELP_ARTICLES.map(helpHref)]
        await writeFile(path.resolve(import.meta.dirname, '../web/sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map(url => `  <url><loc>https://airate.tech${url}</loc></url>`).join('\n')}\n</urlset>\n`)
      } finally {
        await server.close()
      }
    },
  }],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  build: {
    outDir: '../web',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      input: {
        terms: path.resolve(import.meta.dirname, 'terms/index.html'),
        privacy: path.resolve(import.meta.dirname, 'privacy/index.html'),
        landing: path.resolve(import.meta.dirname, 'index.html'),
        cabinet: path.resolve(import.meta.dirname, 'cabinet/index.html'),
        help: path.resolve(import.meta.dirname, 'help/index.html'),
      },
    },
  },
  server: {
    proxy: { '/api/v1': accountBackend, '/api': backend, '/shots': backend },
  },
})
