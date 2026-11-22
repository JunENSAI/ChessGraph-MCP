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
| `POST /api/coach/chat` | The coach, streamed as server-sent events |
| `GET /api/coach/status` | `{"mode": "claude" \| "offline", "model": ...}` |

This process starts its own Stockfish engine the first time an `/api/engine`
route is called. The Stockfish MCP server keeps its own separate engine.

## Coach

`backend/coach/` holds the in-app coach.

- **`tools.py`** has twelve tools with the same names and meaning as the MCP
  tools: `get_player_summary`, `get_coaching_brief`, `list_games`,
  `get_game_moves`, `get_blunders`, `find_position_occurrences`,
  `lookup_opening`, `get_position_context`, `get_position_moves`,
  `analyze_position`, `compare_move` and `validate_line`.
  - They call the repositories in-process, and inputs are validated with
    Pydantic.
  - Limits are tighter than the MCP servers' limits.
  - The player is never an argument; it comes from `CHESS_USERNAME`.
  - Every result is redacted: the owner's account becomes `you` and anyone
    else becomes `opponent`.
- **`prompt.py`** holds the fixed system prompt (cached) and builds the user
  turn from the board context.
- **`providers.py`** has two providers:
  - `ClaudeProvider` runs a manual streamed tool loop: at most 8 rounds,
    results returned in one message, `is_error` on failure, and handling for
    `refusal`, `pause_turn` and `max_tokens`.
  - `OfflineProvider` runs a fixed tool plan and a text template.

`POST /api/coach/chat` takes:

```json
{"question": "...", "fen": "...", "view": "training|review", "summary": "",
 "profile": "", "game_id": null, "played": null, "history": []}
```

It answers with `text/event-stream`. Each `data:` line is one JSON event:

| Event | Fields |
| --- | --- |
| `start` | `mode`, `model` |
| `tool_start` | `tool`, `source` |
| `tool_end` | `tool`, `source`, `ok` |
| `text` | `text` (append) |
| `done` | `mode`, `stop_reason` |
| `error` | `message` |

The coach reads these `.env` settings:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | empty | Empty means offline mode |
| `COACH_MODE` | `auto` | `auto`, `claude` or `offline` |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Model for the tool loop |
| `CLAUDE_EFFORT` | `low` | `low` to `max` |
| `CLAUDE_REFUSAL_FALLBACK` | `default` | `off` disables the server-side fallback |
