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
| `GET /api/explorer?fen=` | Graph v2 moves (book, yours, opponents'), context, and your games through the position; an unknown position is an empty answer, not a 404 |
| `POST /api/engine/analyze` | Bounded Stockfish search |
| `POST /api/engine/compare` | Same-root played move versus best move |
| `POST /api/engine/validate` | Legal replay of a UCI line |
| `POST /api/engine/play` | `{fen, elo, movetime_ms}`: one opponent move with `UCI_LimitStrength`/`UCI_Elo` (1320–3190, `null` = full strength), 50–3000 ms |
| `POST /api/coach/chat` | The coach, streamed as server-sent events |
| `GET /api/coach/status` | `{"mode": "claude" \| "offline", "model": ...}` |

This process starts its own Stockfish engine the first time an `/api/engine`
route is called. `POST /api/engine/play` runs a second process
(`backend/opponent.py`) so that a limited-strength opponent never changes an
analysis. The Stockfish MCP server keeps its own separate engine. A Stockfish
process that dies answers 503.

## Coach

`backend/coach/` holds the in-app coach.

- **`tools.py`** has fourteen tools with the same names and meaning as the MCP
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
- **`tools.py`** also has `graph_context(fen, ctx)`. It calls
  `Neo4jRepository.get_style_context` and reduces the result to compact,
  redacted JSON of at most 6,000 characters. It returns `None` when Neo4j
  fails.
- **`prompt.py`** holds the fixed system prompt. It builds one prompt from the
  earlier turns, the board context, the graph context and the question.
- **`providers.py`** has two providers:
  - `ClaudeProvider` runs Claude through the Claude Agent SDK, on the local
    Claude Code login, with no API key.
    - First it fetches the graph context, reported as `get_style_context` on
      the `neo4j` source.
    - Then it runs one `query()` with the coach system prompt and these
      options: `tools=[]`, `setting_sources=[]`, `strict_mcp_config=True`, and
      the fourteen tools as an in-process MCP server (`mcp__coach__*`).
    - Tool calls are serialized, because one Stockfish process serves them.
    - Text streams from partial messages. The turn cap is 8 (`max_turns`).
    - A refusal, a missing login and a missing CLI each end with their own
      `error` message.
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
| `COACH_MODE` | `claude` | `claude` (your Claude Code login) or `offline` |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Model of the Claude Code session |
| `CLAUDE_EFFORT` | `low` | `low` to `max` |
