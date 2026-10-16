import path from 'node:path'
import { readFile, writeFile } from 'node:fs/promises'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { createServer, defineConfig } from 'vite'

// Собранный интерфейс кладётся в ../web и коммитится: start.bat запускает
// программу без Node. Node нужен только для разработки фронта.
const backend = 'http://127.0.0.1:8756'
const accountBackend = 'http://127.0.0.1:8757'

export default defineConfig({
  plugins: [react(), tailwindcss(), {
    name: 'prerender-homepage',
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
        const file = path.resolve(import.meta.dirname, '../web/index.html')
        const html = await readFile(file, 'utf8')
        if (!html.includes('<div id="root"></div>')) throw new Error('Homepage root placeholder is missing')
        await writeFile(file, html.replace('<div id="root"></div>', () => `<div id="root">${renderLandingPage()}</div>`))
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
      },
    },
  },
  server: {
    proxy: { '/api/v1': accountBackend, '/api': backend, '/shots': backend },
  },
})
