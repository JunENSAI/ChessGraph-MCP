import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Connect, type Plugin, type ProxyOptions } from 'vite'

const uiRoot = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(uiRoot, '..')

/**
 * The browser never sees HERMES_API_KEY. It calls the same-origin path
 * `/hermes-api/*`, and the Vite dev/preview server adds the bearer header
 * while proxying to HERMES_API_URL from the project `.env`. `loadEnv` is
 * called with an empty prefix so the unprefixed HERMES_* variables are read
 * server-side only; loading them as VITE_-prefixed would bake the key into
 * the client bundle.
 *
 * `npm run build` emits static files, so a production deployment needs its
 * own reverse proxy (or the Node server) to serve `/hermes-api` the same way.
 */
function hermesApiProxy(mode: string): Record<string, ProxyOptions> {
  const env = loadEnv(mode, projectRoot, '')
  const target = (env.HERMES_API_URL || 'http://127.0.0.1:8642/v1').replace(/\/+$/, '')
  const apiKey = (env.HERMES_API_KEY || '').trim()

  return {
    '/hermes-api': {
      target,
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
          proxyReq.setHeader('authorization', `Bearer ${apiKey}`)
        })
      },
    },
  }
}

function recapApi(): Plugin {
  const handle: Connect.NextHandleFunction = (req, res, next) => {
    const url = req.url?.split('?')[0]
    if (url !== '/api/recap') {
      next()
      return
    }
    const python = path.join(projectRoot, '.venv/bin/python')
    const script = path.join(projectRoot, 'ui/scripts/recap_stats.py')
    const result = spawnSync(python, [script], { cwd: projectRoot, encoding: 'utf8' })
    res.setHeader('content-type', 'application/json; charset=utf-8')
    if (result.status !== 0) {
      res.statusCode = 503
      res.end(JSON.stringify({ error: (result.stderr || 'Recap query failed.').trim() }))
      return
    }
    res.end(result.stdout)
  }

  return {
    name: 'chessgraph-recap',
    configureServer(server) {
      server.middlewares.use(handle)
    },
    configurePreviewServer(server) {
      server.middlewares.use(handle)
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), recapApi()],
  server: { proxy: hermesApiProxy(mode) },
  preview: { proxy: hermesApiProxy(mode) },
}))
