import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Собранный интерфейс кладётся в ../web и коммитится: start.bat запускает
// программу без Node. Node нужен только для разработки фронта.
const backend = 'http://127.0.0.1:8756'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    outDir: '../web',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
  },
  server: {
    proxy: { '/api': backend, '/shots': backend },
  },
})
