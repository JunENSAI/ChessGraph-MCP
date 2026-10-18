# PostgreSQL MCP server

## What this folder provides

This package exposes personal chess history and theory data through eight
curated, read-only MCP tools:

- `list_games` filters games by player, game type, user outcome, ECO code, and
  date;

- `get_game` returns one game's metadata and PGN movetext;

- `get_game_moves` pages through move, clock, FEN, and stored evaluation data;

- `get_player_summary` aggregates results and ratings;

- `get_blunders` finds high-centipawn-loss moves;

- `find_position_occurrences` finds games containing a normalized FEN;

- `lookup_opening` retrieves opening theory for a position;

- `lookup_endgame_positions` retrieves filtered endgame examples.

The `chessgraph://postgres/schema` MCP resource gives agents a compact
description of the tables and field semantics.

## Why PostgreSQL is used

PostgreSQL is the source for ordered, reproducible records:

- one row per game;

- one ordered row per played move;

- stable joins between games and moves;

- opening and endgame reference datasets;

- historical Stockfish values loaded by the ETL process.

Relational queries are appropriate for questions such as:

- “Which rapid games did I lose this month?”

- “What are my largest evaluated mistakes?”

- “How often did this exact position occur?”

- “Which opening or endgame record matches this FEN?”

Neo4j is better for multi-hop position relationships, while the Stockfish
server is better for fresh analysis. PostgreSQL should not be treated as a live
engine or as a graph traversal service.

## How it is implemented

```text
MCP tool in server.py
        │
        ▼
parameterized method in repository.py
        │
        ▼
read-only SQLAlchemy transaction
        │
        ▼
typed result from models.py
```

### `server.py`

The protocol layer defines tool schemas, validates simple arguments, maps
failures to MCP tool errors, publishes the schema resource, and closes the
connection pool during server shutdown.

All tools carry read-only, non-destructive, and idempotent MCP annotations.
The protocol layer does not contain raw SQL.

### `repository.py`

The repository owns fixed SQL statements and result mapping. Queries use bound
parameters rather than interpolating model-provided values. Every operation:

- runs with PostgreSQL's read-only transaction option;

- sets a transaction-local statement timeout;

- clamps results to the configured maximum and an absolute 100-row ceiling;

- selects only from the ETL-created tables.

This is defense in depth. The configured PostgreSQL account should still have
only `CONNECT`, schema `USAGE`, and `SELECT` permissions.

### `models.py`

Pydantic models describe the structured output sent over MCP. They preserve
important distinctions such as:

- `result`, which is recorded from White's perspective;

- `user_outcome`, which is recorded from the ETL user's perspective;

- `turn_color`, which identifies the player who made a move;

- nullable engine fields, which indicate that evaluation backfill may not have
  run for that move.

## Position and move semantics

`game_id` is the internal stable join key. Move identity is
`(game_id, ply_number)`, and `ply_number` starts at 1.

`fen_before_norm`, `fen_after_norm`, and opening/endgame normalized FEN fields
contain four FEN fields. Input FENs are normalized through the package's shared
helper before exact lookup.

`get_game_moves` accepts `start_ply` because a game can exceed the 100-row
response limit. Fetch a long game in pages:

```text
get_game_moves(game_id=42, start_ply=1, limit=100)
get_game_moves(game_id=42, start_ply=101, limit=100)
```

When `get_blunders` has no `player`, it returns moves made by the configured
data owner using `games.user_color`. Supplying a player instead filters moves
made by that named player.

`get_player_summary` defaults to `CHESS_USERNAME`; pass `username` explicitly
to summarize another player.

## Configuration

Required variables:

```text
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
```

Optional variables:

```text
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_STATEMENT_TIMEOUT_MS=10000
MCP_MAX_RESULTS=100
CHESS_USERNAME=<ETL data owner>
```

Use credentials for the database containing `games`, `game_moves`,
`opening_theory`, and `endgame_theory`.

## Choosing the right tool

- Start with `list_games` when the game is not yet known.

- Use `get_game` for metadata and raw PGN.

- Use `get_game_moves` for exact move-by-move evidence.

- Use `get_blunders` to identify positions worth deeper analysis.

- Use `find_position_occurrences` to connect a current position to history.

- Use `lookup_opening` and `lookup_endgame_positions` for reference data.

After selecting a critical move, send its pre-move FEN and played UCI move to
the Stockfish `compare_move` tool. Use Neo4j when the question concerns
transpositions, theory-versus-personal choices, or repeated graph patterns.

## Extending safely

Add a new Pydantic output model, then a fixed repository query, then a thin MCP
tool. Keep filters parameterized and indexed, add a mandatory result limit, and
test the generated parameters with a fake engine. Do not add arbitrary SQL or
write operations to this server.
