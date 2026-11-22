import type { ExplorerJson } from '../lib/explorer'

const cache = new Map<string, Promise<ExplorerJson>>()
const CACHE_LIMIT = 200

function key(fen: string): string {
  // Move counters do not change the graph key.
  return fen.trim().split(/\s+/).slice(0, 4).join(' ')
}

/** Graph v2 moves for a position. Answers are cached per position for the page's lifetime. */
export function loadExplorer(fen: string): Promise<ExplorerJson> {
  const id = key(fen)
  const cached = cache.get(id)
  if (cached) return cached
  const request = (async () => {
    let response: Response
    try {
      response = await fetch(`/api/explorer?${new URLSearchParams({ fen })}`)
    } catch {
      throw new Error('The API is not reachable.')
    }
    if (!response.ok) {
      let detail = `Explorer request failed (${response.status}).`
      try {
        const body = (await response.json()) as { error?: string }
        if (body.error) detail = body.error
      } catch {
        // Keep the status message.
      }
      throw new Error(detail)
    }
    return (await response.json()) as ExplorerJson
  })()
  request.catch(() => cache.delete(id))
  if (cache.size >= CACHE_LIMIT) cache.delete(cache.keys().next().value!)
  cache.set(id, request)
  return request
}
