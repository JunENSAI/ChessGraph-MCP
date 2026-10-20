# ChessGraph retrieval API

The UI reads facts from this process. Hermes keeps the MCP servers and explains
what those tools return. Both call the repositories in `chess_mcp/`.

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The Vite dev server proxies `/api` to `BACKEND_URL` (default
`http://127.0.0.1:8000`).

| Path | Read |
| --- | --- |
| `GET /api/recap` | Rating-band counts from PostgreSQL |
| `GET /api/games` | Filtered game list for My games. `limit` is at most 100 |
| `GET /api/games/{id}` | One game |
| `GET /api/games/{id}/moves` | Ordered moves, clocks, and stored evaluations. `limit` is at most 100 |
| `GET /api/lessons/openings?color=` | Most-played openings for `white` or `black`, with one theory line |
| `GET /api/lessons/endgames` | Technique positions from the elo tier nearest the player's rating |
| `GET /api/player` | Summary for `CHESS_USERNAME` when `username` is omitted |
| `GET /api/openings?fen=` | Opening-file rows for that position |
| `GET /api/positions?fen=` | Neo4j context and moves |
| `POST /api/engine/analyze` | Bounded Stockfish search |
| `POST /api/engine/compare` | Same-root played move versus best move |
| `POST /api/engine/validate` | Legal replay of a UCI line |

Training and My games call the lesson and game routes above. Omit `player` and
`username` to use `CHESS_USERNAME` from `.env`. Opening lessons are the lines
the account has played most often; each row includes one `opening_theory`
line when the name matches. Endgame lessons are one position per type from
the elo tier closest to the account's average rating. The game list is paged
with `game_type`, `limit`, and `offset`. A move page includes the stored
centipawn loss and `best_move_uci` the review uses as its key moment.

An empty result is an empty list. If PostgreSQL is down the route returns
503 and `{"error": "PostgreSQL is not accepting connections."}`. The UI shows
that error. It does not fill the page with sample games.

This process starts its own Stockfish engine the first time an `/api/engine`
route is called. The Stockfish MCP server keeps a separate engine for Hermes.
