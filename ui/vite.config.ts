import { fileURLToPath } from 'node:url'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'

const uiRoot = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(uiRoot, '..')

/**
 * Dev and preview proxy. `/api` goes to the FastAPI retrieval process, which
 * also runs the coach (`POST /api/coach/chat`, server-sent events). The model
 * key and database credentials stay in that process: the browser never sees
 * them. `loadEnv` uses an empty prefix so .env values stay off the bundle.
 *
 * `npm run build` emits static files, so a production deployment needs its
 * own reverse proxy for `/api`.
 */
function localProxies(mode: string): Record<string, ProxyOptions> {
  const env = loadEnv(mode, projectRoot, '')
  const backendTarget = (env.BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')

  return {
    '/api': {
      target: backendTarget,
      changeOrigin: true,
      // One coach answer may run several tool calls; keep the stream open.
      timeout: 300_000,
      proxyTimeout: 300_000,
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: { proxy: localProxies(mode) },
  preview: { proxy: localProxies(mode) },
}))
