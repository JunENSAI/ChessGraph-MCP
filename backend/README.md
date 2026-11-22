# ChessGraph retrieval API

The UI reads facts from this process. The MCP servers expose the same
repositories in `chess_mcp/` to Claude.

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The Vite dev server proxies `/api` to `BACKEND_URL` (default
`http://127.0.0.1:8000`).

| Path | Read |
| --- | --- |
| `GET /health` | Liveness check |
| `GET /api/recap` | Rating-band counts from PostgreSQL |
| `GET /api/games` | Filtered game list |
| `GET /api/games/{id}` | One game |
| `GET /api/games/{id}/moves` | Ordered moves |
| `GET /api/player` | Summary for `CHESS_USERNAME` when `username` is omitted |
| `GET /api/lessons/openings?color=` | Opening lines to drill for one colour |
| `GET /api/lessons/endgames` | Endgame benchmarks for the player's rating tier |
| `GET /api/coach/brief` | Strengths, weakest family, repeated mistakes, four tasks |
| `GET /api/coach/plan` | Ranked training plan |
| `GET /api/openings?fen=` | Opening-file rows for that position |
| `GET /api/positions?fen=` | Neo4j context and moves |
| `POST /api/engine/analyze` | Bounded Stockfish search |
| `POST /api/engine/compare` | Same-root played move versus best move |
| `POST /api/engine/validate` | Legal replay of a UCI line |

This process starts its own Stockfish engine the first time an `/api/engine`
route is called. The Stockfish MCP server keeps its own separate engine.
