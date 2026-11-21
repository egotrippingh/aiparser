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
    async writeBundle() {
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
        const helpTemplate = await readFile(path.resolve(import.meta.dirname, '../web/docs/index.html'), 'utf8')
        const { createSearchAPI } = await import('fumadocs-core/search/server')
        const api = createSearchAPI('simple', {
          indexes: HELP_ARTICLES.map(article => ({ title: article.title, description: article.summary, url: helpHref(article), content: helpSearchContent(article) })),
        })
        await writeFile(path.resolve(import.meta.dirname, '../web/assets/help-search.json'), await (await api.staticGET()).text())
        for (const article of HELP_ARTICLES) {
          const articleDir = path.resolve(import.meta.dirname, `../web/docs/${article.slug}`)
          await mkdir(articleDir, { recursive: true })
          const prerendered = helpTemplate.replace('<title>Документация AIRate</title>', () => renderHelpHead(article)).replace('<div id="root"></div>', () => `<div id="root">${renderHelpPage(article)}</div>`)
          await writeFile(path.resolve(articleDir, 'index.html'), prerendered)
          if (article === HELP_ARTICLES[0]) await writeFile(path.resolve(import.meta.dirname, '../web/docs/index.html'), prerendered)
        }
        const urls = ['/', ...HELP_ARTICLES.map(helpHref)]
        await writeFile(path.resolve(import.meta.dirname, '../web/sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map(url => `  <url><loc>https://airate.tech${url}</loc></url>`).join('\n')}\n</urlset>\n`)
        const integrations = path.resolve(import.meta.dirname, '../integrations')
        const requirements = await readFile(path.join(integrations, 'requirements-mcp.txt'), 'utf8')
        const dependencies = requirements.split(/\r?\n/).map(line => line.trim()).filter(line => line && !line.startsWith('#'))
        const script = (await readFile(path.join(integrations, 'airate_mcp.py'), 'utf8')).replace(/\r\n/g, '\n')
        const mcpAssets = path.resolve(import.meta.dirname, '../web/assets/mcp')
        await mkdir(mcpAssets, { recursive: true })
        await writeFile(path.join(mcpAssets, 'airate_mcp.py'), `# /// script\n# requires-python = ">=3.12"\n# dependencies = ${JSON.stringify(dependencies)}\n# ///\n\n${script}`)
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
        missing: path.resolve(import.meta.dirname, '404/index.html'),
        terms: path.resolve(import.meta.dirname, 'terms/index.html'),
        privacy: path.resolve(import.meta.dirname, 'privacy/index.html'),
        landing: path.resolve(import.meta.dirname, 'index.html'),
        cabinet: path.resolve(import.meta.dirname, 'cabinet/index.html'),
        docs: path.resolve(import.meta.dirname, 'docs/index.html'),
      },
    },
  },
  server: {
    proxy: { '/api/v1': accountBackend, '/api': backend, '/shots': backend },
  },
})
