import { defineConfig, mergeConfig } from "vite"
import base from "../vite.config.ts"

const fixture = "http://127.0.0.1:8793"

export default defineConfig(mergeConfig(base, {
  define: { "import.meta.env.VITE_ACCOUNT_API_URL": '""' },
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
    proxy: { "/api/v1": fixture, "/api": fixture, "/__qa": fixture },
  },
}))
