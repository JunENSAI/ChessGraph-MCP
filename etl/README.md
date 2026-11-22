# ETL

The loaders here are the only code that writes to the databases. The MCP
servers and the retrieval API only read. All loaders take their connection
settings from the repository `.env` through `chess_mcp.config`:

- `postgres_url()` builds the PostgreSQL URL with `sqlalchemy.URL.create`, so
  `POSTGRES_PASSWORD` holds the literal password (special characters such as
  `@` need no escaping).
- `base_data_dir()` reads `BASE_DATA_DIR` and falls back to `data/` in the
  repository.

## Order

```bash
# 1. Schema. openings.sql and endgame.sql only create their tables;
#    games.sql DROPS and recreates games and game_moves.
psql -f etl/sql_files/openings.sql -f etl/sql_files/endgame.sql -f etl/sql_files/games.sql

# 2. Theory and games into PostgreSQL
uv run python etl/postgres_db/postgres_load.py

# 3. Stockfish evaluations for every unevaluated move (depth = STOCKFISH_DEPTH)
uv run python etl/postgres_db/load_stockfish_eval.py

# 4. Read-path indexes (adds indexes only; safe to re-run)
psql -f etl/sql_files/migrations/001_read_indexes.sql

# 5. PostgreSQL to Neo4j graph (schema v2); --reset deletes the chess labels only
uv run python etl/neo4j_db/neo4j_load.py --dry-run
uv run python etl/neo4j_db/neo4j_load.py --reset
```

| Step | Reads | Writes |
| --- | --- | --- |
| `load_opening.py` | `data/opening_theory/chess_openings.parquet` | `opening_theory` (truncate + reload) |
| `load_endgame.py` | `data/endgame_theory/endgame_atlas_bench.csv` | `endgame_theory` (truncate + reload) |
| `load_chessgame.py` | `data/my_games/{blitz,rapid,bullet,daily,bot}.pgn` | `games`, `game_moves` |
| `load_stockfish_eval.py` | `game_moves` without evaluations | `eval_cp_before/after`, `cp_loss`, `best_move_uci`; a game whose stored moves do not replay is logged and skipped |
| `migrations/001_read_indexes.sql` | — | indexes on `game_moves(fen_after_norm)`, `lower(white_username)`, `lower(black_username)` |
| `neo4j_load.py` | all four tables | Neo4j chess labels only: `Position`, `Game`, `Player`, `Opening`, `OpeningFamily`, `EndgamePattern`, `ChessGraphMeta` and their edges |

`CHESS_USERNAME` decides the perspective columns (`user_color`, `user_elo`,
`user_outcome`) at load time. It lives only in `.env`.

See `postgres_db/dbeaver_init.md` for creating the database and role, and
`neo4j_db/neo4j_init.md` for the graph model and example queries.
