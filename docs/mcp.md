# ChessGraph MCP servers

ChessGraph exposes three independent, read-only MCP servers for local agents:

- `chessgraph-postgres-mcp` queries personal game telemetry and theory tables.
- `chessgraph-neo4j-mcp` traverses the positional knowledge graph.
- `chessgraph-stockfish-mcp` performs reproducible engine analysis.

Each server uses the official Python MCP SDK v2 `MCPServer` API and the stdio
transport. Stdio is intended for a trusted local MCP host such as Hermes-Agent.
No server listens on a network port.

## Install

1. Copy `.env.template` to `.env` and set the database credentials and
   `STOCKFISH_PATH`.
2. Use dedicated read-only PostgreSQL and Neo4j accounts where possible.
3. Install the project and executable entry points:

```bash
uv sync
```

The three executables are installed in `.venv/bin/`. They must be launched by
an MCP client because stdin and stdout carry protocol messages. Application
logs are written to stderr.

## Hermes-Agent

Merge `agent/hermes-mcp.example.yaml` into `~/.hermes/config.yaml`. Adjust the
absolute executable paths if the repository is elsewhere. Export the referenced
credentials before starting Hermes; do not put real passwords in a committed
configuration file.

Hermes prefixes the tools with their server name. For example,
`get_game_moves` from `chess_postgres` is registered as
`mcp_chess_postgres_get_game_moves`.

PostgreSQL and Neo4j tools may run in parallel. Stockfish calls must remain
serialized because one persistent UCI process serves that MCP server.

## PostgreSQL tools

- `list_games`: filter games by type, outcome, opening, and date.
- `get_game`: retrieve one game's metadata.
- `get_game_moves`: retrieve its ordered move/evaluation records.
- `get_player_summary`: aggregate a player's performance, defaulting to
  `CHESS_USERNAME`.
- `get_blunders`: list the data owner's largest evaluated mistakes.
- `find_position_occurrences`: find personal games containing a FEN position.
- `lookup_opening`: retrieve opening theory by FEN or ECO code.
- `lookup_endgame_positions`: retrieve matching endgame benchmarks.

The `chessgraph://postgres/schema` resource documents table and field semantics.
Every query is parameterized, runs in a read-only transaction with a statement
timeout, and has a bounded result count. There is no arbitrary SQL tool.

Stored `cp_loss` values are only available where the Stockfish ETL backfill has
run. User-perspective fields depend on `CHESS_USERNAME` at ETL time.

## Neo4j tools

- `get_position_context`: retrieve a position and its classifications.
- `get_position_moves`: compare personal and theory continuations.
- `find_transpositions`: find bounded paths from a normalized position.
- `get_game_blunders`: retrieve graph-linked mistakes for a game.
- `get_recurring_blunder_positions`: find repeated high-loss positions.
- `get_endgame_context`: retrieve endgame pattern and benchmark context.

The `chessgraph-neo4j://schema` resource documents labels, relationships, and
ETL caveats. Traversals are anchored, parameterized, depth-capped, and
result-capped. There is no arbitrary Cypher tool.

Graph values reflect the current loader:

- `visit_count` is not a global popularity count.
- computed `material_sig` values may not match dataset `endgame_type` names.
- `BLUNDERED_IN` identity includes the position endpoint, game endpoint, and
  ply; repeated ETL syncs update the same event.

## Stockfish tools

- `analyze_position`: bounded MultiPV analysis using depth, nodes, or time.
- `compare_move`: compare a legal played move with the best move from the same
  root position and search budget.
- `validate_line`: replay UCI moves and return legal SAN/FEN evidence.

The `chessgraph-stockfish://capabilities` resource explains score semantics.
Scores identify their point of view and retain mate scores separately from
centipawns. Centipawn loss is returned only when both comparable scores are
ordinary centipawn scores. Principal variations are replayed legally and
returned in UCI and SAN.

Depth, time, node, and MultiPV requests are clamped by environment limits.
Engine version, options, search limit, depth, nodes, and elapsed engine time are
returned as provenance where Stockfish provides them.

## Inspect and test

Run the unit suite:

```bash
uv run pytest
```

Open one server in the official MCP Inspector:

```bash
uv run mcp dev chess_mcp/postgres/server.py
uv run mcp dev chess_mcp/neo4j/server.py
uv run mcp dev chess_mcp/stockfish/server.py
```

Database integration tests are opt-in so the normal suite never depends on
local services. Set `CHESSGRAPH_RUN_INTEGRATION=1` after configuring `.env`.

## Read-only roles

The application prevents writes at the tool and transaction layers, but
database permissions are the final boundary.

For PostgreSQL, grant the MCP account only `CONNECT`, schema `USAGE`, and
`SELECT` on `games`, `game_moves`, `opening_theory`, and `endgame_theory`.
Configure the role with a statement timeout as defense in depth.

For Neo4j Enterprise, assign a role limited to graph reads. Neo4j Community has
less granular authorization, so keep it bound locally and use credentials
dedicated to this project.

## Troubleshooting

- `Connection closed`: run the absolute executable manually to reveal stderr,
  and confirm `uv sync` created the entry point.
- Configuration error: compare exported variables with `.env.template`.
- Empty evaluations: run the existing Stockfish ETL backfill; the MCP server
  intentionally does not mutate database rows.
- FEN not found: database lookups use the ETL's first four FEN fields
  (placement, turn, castling, en-passant).
- Stockfish timeout: lower depth/MultiPV or raise the Hermes tool timeout within
  the local resource limits.
