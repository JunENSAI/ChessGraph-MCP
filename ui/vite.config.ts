import { fileURLToPath } from 'node:url'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'

const uiRoot = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(uiRoot, '..')

/**
 * Dev and preview proxies. The browser never sees HERMES_API_KEY or database
 * credentials. `/api` goes to the FastAPI retrieval process. `/hermes-api`
 * goes to the Hermes gateway, and this server adds the bearer header.
 * `loadEnv` uses an empty prefix so those variables stay off the client bundle.
 *
 * `npm run build` emits static files, so a production deployment needs its
 * own reverse proxy for both paths.
 */
function localProxies(mode: string): Record<string, ProxyOptions> {
  const env = loadEnv(mode, projectRoot, '')
  const hermesTarget = (env.HERMES_API_URL || 'http://127.0.0.1:8642/v1').replace(/\/+$/, '')
  const apiKey = (env.HERMES_API_KEY || '').trim()
  const backendTarget = (env.BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')

  return {
    '/api': {
      target: backendTarget,
      changeOrigin: true,
    },
    '/hermes-api': {
      target: hermesTarget,
      changeOrigin: true,
      secure: false,
      // Long budget: one coach answer may run several MCP tool calls.
      timeout: 300_000,
      proxyTimeout: 300_000,
      rewrite: requestPath => requestPath.replace(/^\/hermes-api/, ''),
      configure: proxy => {
        if (!apiKey) {
          console.warn(
            '[hermes-api] HERMES_API_KEY is empty; /hermes-api requests will be rejected with 401. ' +
              'Set it in the project .env to match API_SERVER_KEY in ~/.hermes/.env.',
          )
          return
        }
        proxy.on('proxyReq', proxyReq => {
          // The gateway's API server answers 403 to ANY request carrying an
          // Origin header (it accepts no cross-origin browser callers, and a
          // preflight gets 403 too). This proxy is the client, not the browser,
          // so drop the browser provenance headers before forwarding.
          proxyReq.removeHeader('origin')
          proxyReq.removeHeader('referer')
          proxyReq.setHeader('authorization', `Bearer ${apiKey}`)
        })
      },
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: { proxy: localProxies(mode) },
  preview: { proxy: localProxies(mode) },
}))
