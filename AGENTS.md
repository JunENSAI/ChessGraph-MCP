# ChessGraph

Local evidence layer for personalized chess coaching. Three layers stay separate:

- **ETL writes.** `etl/postgres_db/` and `etl/neo4j_db/` load games, theory, the Stockfish backfill, and the Neo4j graph. Loaders mutate data. MCP servers never call them.
- **MCP reads.** Three stdio servers in `chess_mcp/`: PostgreSQL (games and telemetry), Neo4j (position graph), and Stockfish (UCI). Tools are read-only, parameterized, and bounded. There is no arbitrary SQL or Cypher tool.
- **The model explains.** State only what those tools returned. Do not invent evaluations, lines, ratings, or personal history.

Persona and player facts live in `agent/SOUL.md`, `agent/MEMORY.md`, and `agent/USER.md`. Hermes loads `SOUL.md` and `memories/` only from `$HERMES_HOME`, not from this repository. Copy them as described in `agent/README.md`. This file is the project brief Hermes loads when its working directory is the repo.

## Player

The human is Junior. Their Chess.com account name is `CHESS_USERNAME` in the local `.env`, which is not committed. Do not copy that value into this file, `agent/SOUL.md`, `agent/MEMORY.md`, or `agent/USER.md`. Omit `username` on `get_player_summary` so the PostgreSQL server reads `CHESS_USERNAME`, then use the `username` field the tool returns.

## Evidence order

For a coaching answer, gather evidence in this order, then explain it:

1. PostgreSQL: game, moves, clocks, stored centipawn loss, openings, and endgames. `get_player_summary` and blunder lookups default to `CHESS_USERNAME`.
2. Neo4j: theory versus personal moves, transpositions, recurring positions, and endgame context. Traversals stay inside `NEO4J_MAX_PATH_DEPTH`.
3. Stockfish: `analyze_position` or `compare_move` from the same root and the same search budget. Scores are from the side to move at the root. Centipawn loss exists only when both scores are centipawn scores.
4. `validate_line` before citing any continuation. Quote the legal UCI, SAN, and resulting FEN from the tool.

PostgreSQL and Neo4j reads may run in parallel. Stockfish calls stay serial because one UCI process serves that server.

If a tool returns nothing, say the evidence is missing. Do not fill the gap with a plausible line.

## Position identity

PostgreSQL and Neo4j share a four-field normalized FEN:

```text
piece placement · side to move · castling rights · en-passant target
```

Move counters are dropped so transpositions share one key. Stockfish receives a valid six-field FEN built from that key.

## Commands

```bash
uv sync
uv run pytest
CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py

uv run python etl/postgres_db/postgres_load.py
uv run python etl/postgres_db/load_stockfish_eval.py
uv run python etl/neo4j_db/neo4j_load.py

cd ui && npm install
cd ui && npm run dev
cd ui && npm test
cd ui && npm run build
```

Configuration comes from `.env`, copied from `.env.template`. Do not commit secrets. The coach in `ui/src/services/coach.ts` calls the Hermes gateway through the Vite proxy path `/hermes-api`, which forwards to `HERMES_API_URL` and adds the `HERMES_API_KEY` bearer header server-side. `HERMES_API_KEY` must match `API_SERVER_KEY` in `~/.hermes/.env`. Keep that key on a local server and never expose it as a `VITE_` variable or read it in the browser. Board content still comes from `ui/src/data/demo.ts`.

## Layout

- `chess_mcp/` — MCP servers, models, and repositories
- `etl/` — writers and the SQL schema
- `ui/` — React coach, still on demo data
- `agent/` — Hermes persona, memory seeds, and `hermes-mcp.example.yaml`
- `docs/mcp.md` — server contracts and security
- `CHESS.md`, `STOCKFISH.md` — domain references
