# Changelog

The rework from Hermes-Agent to Claude is delivered in batches on the
`rework/claude-platform` branch, one commit per batch. Each entry says what
changed, why, and the exact checks that ran.

## Batch 1: cleanup, facts, config

### Why

- PostgreSQL could not be reached with psql or DBeaver using the `.env` values.
- Some documentation stated wrong chess and engine facts.
- Dead code and unused files had piled up.

### Changed

**Connection settings**

- `chess_mcp/config.py` adds `postgres_url()`, which builds the URL with
  `sqlalchemy.URL.create`. `POSTGRES_PASSWORD` is now the literal password.
  - Before, URLs were assembled with f-strings, so an `@` in the password had
    to be written `%40` in `.env`.
  - psql and DBeaver read the raw value and were refused.
  - The local `.env` was updated to match: the escape was replaced by the real
    character.
- The ETL scripts `postgres_load.py`, `load_stockfish_eval.py` and
  `neo4j_load.py` read their settings through `chess_mcp.config`:
  - `postgres_url()`, `get_neo4j_settings()`, `base_data_dir()`,
    `get_chess_username()`, `get_setting()` and `get_int_setting()`.
  - This replaces their own `os.getenv` defaults and the hard-coded home-folder
    data path.
  - `BASE_DATA_DIR` is now documented in `.env.template`.
- `MAX_PATH_DEPTH = 4` lives in `chess_mcp/config.py` and is the single ceiling
  for graph traversals. The setting used to allow 8 while the repository
  silently capped at 4.

**Consistency**

- The Neo4j MCP server now matches the PostgreSQL and Stockfish servers:
  - it logs through `errors.tool_failure`;
  - it configures stderr logging in `main()`;
  - it exports `server = mcp`.
- `get_game_blunders` now rejects a non-positive `game_id`.

**Privacy**

- A Chess.com account name was written in a comment in
  `etl/sql_files/games.sql`. It has been removed, and no tracked file contains
  it any more.

**Removed**

| What | Why |
| --- | --- |
| Root `main.py` | Hello-world stub |
| Empty `etl/README.md` | Replaced by a real ETL guide |
| `QueryMetadata` and `PositionKey` in `chess_mcp/models.py` | Unused |
| `chess.replay_uci_line` | Duplicated `StockfishService.validate_line`. Its illegal-move test moved to `tests/test_stockfish_engine.py`. |
| Dependencies `polars` and `python-chess` | `polars` was unused. `python-chess` only re-exports `chess`. |
| UI: `formatEval`, `scoreRate`, `combine`, `drillLength`, `courseNote`, `splitSession`, `loadCoachingBrief` | Unused |
| UI: types `CoachingBrief`/`Line`/`Split`, `TrainingTrack`, `LibraryGame`, `RatingBand`, `EndgameStat` | Unused |
| UI: `ModeSpec.lazy` and an unreachable `split:` branch in `TrainingView` | Dead code |

**Facts corrected**

- `CHESS.md`:
  - **Piece movement:** how the queen, rook and bishop move and are blocked. Pawn captures, en passant, optional double step and promotion.
  - **First-move advantage vs initiative:** these are different things.
  - **Time controls:**
    - World Championship: 120 min for 40 moves, then 30 min with +30 s from move 41.
    - FIDE rapid: more than 10 and less than 60 min. Chess.com rapid: 10 min or more.
    - Titled Tuesday: 3+1.
    - Daily: `1/86400`.
  - **Checkmate:** means no legal move at all.
  - **Pins:** absolute pins (to the king) differ from relative pins.
  - **Castling:** the conditions are now listed.
  - **Queen's Gambit:** the opening, and the series (October 2020).
- `STOCKFISH.md`: HalfKP is marked historical. A new section covers
  HalfKAv2_hm (kings included, mirrored, 22,528 inputs) and the big/small
  networks in Stockfish 17.x.
- `data/README.md`:
  - draws (`1/2-1/2`);
  - increment and daily time-control formats;
  - clock comments;
  - the theory depth now matches `CHESS.md`;
  - a correct endgame description with the dataset's White-first material
    notation.
- `docs/mcp.md`, `chess_mcp/postgres/README.md`:
  - there are 9 PostgreSQL tools, including `get_coaching_brief`;
  - `lookup_opening` takes only a FEN;
  - the `list_games` filters are listed accurately.
- `chess_mcp/stockfish/README.md`: depth defaults are 6 and 9, matching
  `.env.template`.
- `backend/README.md`: all 15 routes are listed.
- `ui/README.md` is rewritten: there is no demo data, and the current modes and
  structure are described.
- `etl/neo4j_db/neo4j_init.md`:
  - the blunder query used `BLUNDERED_IN` in the wrong direction;
  - traversal depth is 4, not 20.
- `AGENTS.md` no longer mentions the deleted `demo.ts`.

### Tested

| Command | Result |
| --- | --- |
| `uv run pytest` | 74 passed, 3 skipped (integration) |
| `CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py` | 3 passed against live PostgreSQL, Neo4j and Stockfish |
| `cd ui && npm test` | 71 passed |
| `cd ui && npm run lint` | 0 errors; the 3 existing warnings were left for the UI batch |
| `cd ui && npm run build` | built |
| psql read-only login with the `.env` values | games 4,595; game_moves 388,522 (all evaluated); opening_theory 3,704; endgame_theory 35,006 |
| SQLAlchemy through `postgres_url()` | 4,595 games |
| ETL entry scripts imported with the shared settings | data folder found, username resolved |

New tests:

- `tests/test_config.py`: the password keeps `@ : / %40` literally and they
  are escaped in the rendered URL; the settings use that URL; the path depth
  cannot exceed 4; the default data folder.
- `tests/test_stockfish_engine.py`: `validate_line` reports the ply of an
  illegal move without starting the engine.
