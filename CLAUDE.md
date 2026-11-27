# ChessGraph

ChessGraph is a local evidence layer for personalized chess coaching. It keeps
three layers separate:

- **ETL writes.** `etl/postgres_db/` and `etl/neo4j_db/` load games, theory, the
  Stockfish backfill, and the Neo4j graph. Loaders mutate data. The MCP servers
  and the API never call them.
- **MCP and the API read.** There are three stdio servers in `chess_mcp/`:
  PostgreSQL (games and telemetry), Neo4j (position graph), and Stockfish (UCI).
  The FastAPI process in `backend/` calls the same repositories for the UI.
  Every tool is read-only, parameterized, and bounded. There is no arbitrary
  SQL or Cypher tool.
- **Claude explains.** State only what those tools returned. Do not invent
  evaluations, lines, ratings, or personal history.

The coaching persona and skills ship as the Claude Code plugin in
`plugins/chessgraph/`:

- the `chess-coach` agent;
- the skills `/chessgraph:explain-position`, `review-game`, `training-plan`,
  `opening-check`, and `status`;
- the three MCP servers.

See `docs/plugin.md`.

## Player

The player is Junior, a data scientist who works directly in code.

- **Account name.** Junior's Chess.com account name is `CHESS_USERNAME` in the
  local `.env`, which is not committed. Never copy that value into a tracked
  file, a commit, or memory. Omit `username` on `get_player_summary` so the
  server reads it, then use the `username` field the tool returns.
- **Style.** Junior prefers positional chess: pawn structure, weak squares,
  piece activity, space, outposts, and prophylaxis rather than speculative
  tactics.
- **Answers.** Junior wants concise, concrete coaching: the evaluation, the
  single move that follows, and a short reason. State what the tools showed and
  what is still missing.

## Evidence order

For a coaching answer, gather evidence in this order, then explain it:

1. **PostgreSQL:** the game, moves, clocks, stored centipawn loss, openings,
   endgames, and the coaching brief.
2. **Neo4j:** theory versus personal moves, transpositions, recurring
   positions, and endgame context. Traversals stay within
   `NEO4J_MAX_PATH_DEPTH`, which is at most 4.
3. **Stockfish:** `analyze_position` or `compare_move` from the same root with
   the same search budget. Scores are from the side to move at the root.
   Centipawn loss exists only when both scores are centipawn scores.
4. **`validate_line`** before citing any continuation. Quote the legal UCI, SAN,
   and resulting FEN from the tool.

PostgreSQL and Neo4j reads may run in parallel. Stockfish calls stay serial
because one UCI process serves that server.

If a tool returns nothing, say the evidence is missing. Do not fill the gap with
a plausible line.

## Position identity

PostgreSQL and Neo4j share a four-field normalized FEN:

```text
piece placement · side to move · castling rights · en-passant target
```

Move counters are dropped so transpositions share one key. Stockfish receives a
valid six-field FEN built from that key.

## Commands

```bash
uv sync
uv run pytest
CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py
uv run chessgraph-status      # are PostgreSQL, Neo4j and Stockfish up?
uv run chessgraph-smoke       # start each MCP server over stdio, list tools, call one

uv run python etl/postgres_db/postgres_load.py
uv run python etl/postgres_db/load_stockfish_eval.py
uv run python etl/neo4j_db/neo4j_load.py

uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

cd ui && npm install
cd ui && npm run dev
cd ui && npm test
cd ui && npm run build

claude plugin validate plugins/chessgraph
```

Configuration comes from `.env`, copied from `.env.template`. Do not commit
secrets. `POSTGRES_PASSWORD` is the literal password: `chess_mcp.config`
escapes it when it builds the URL. The UI proxies `/api` to the FastAPI
process. A model key, when one is added, stays server-side and is never a
`VITE_` variable.

## Working rules

- Every change ships with tests and a `CHANGELOG.md` entry that records the
  commands run and their results.
- Database writes happen only in `etl/`. The Neo4j database is shared with
  other projects, so chess ETL may only touch chess labels.

## Layout

- `chess_mcp/` — MCP servers, models, repositories, `status` and `smoke` checks
- `backend/` — FastAPI reads for the UI, and `backend/coach/`, the in-app coach (Claude on the local Claude Code login with a Neo4j graph-context pre-fetch, or offline evidence mode)
- `etl/` — writers and the SQL schema
- `ui/` — React coach, reading the retrieval API
- `plugins/chessgraph/` — Claude Code plugin: MCP servers, coach agent, skills
- `.claude-plugin/marketplace.json` — local marketplace for installing the plugin
- `docs/` — MCP contracts and security, plugin guide
- `CHESS.md`, `STOCKFISH.md` — domain references
