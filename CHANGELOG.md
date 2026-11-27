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

## Batch 2: Claude Code plugin replaces the Hermes host

### Why

- The MCP host moves from Hermes-Agent to Claude Code.
- Hermes was never fully configured locally: `~/.hermes` had no `config.yaml`
  and no seeds.
- Packaging the servers, the persona, and the coaching workflows as a plugin
  makes them installable and repeatable.

### Changed

**Plugin `plugins/chessgraph/`**

- `.claude-plugin/plugin.json` declares one setting, `userConfig.chessgraph_home`
  (type `directory`): the path of the checkout.
- `.mcp.json` starts `postgres`, `neo4j` and `stockfish` with
  `uv run --quiet --directory ${user_config.chessgraph_home} chessgraph-<name>-mcp`.
  The servers read the repository `.env`, so no credential is stored in the
  plugin.
- `agents/chess-coach.md` carries the persona, evidence order and evidence
  rules from the old `agent/SOUL.md`. Its tools are limited to
  `mcp__plugin_chessgraph_{postgres,neo4j,stockfish}__*`.
- Five skills, each naming the exact tools and the "missing evidence" rule:
  - `explain-position` (FEN to evaluation, move, why, and your history);
  - `review-game` (three largest mistakes, same-root `compare_move`, one
    lesson);
  - `training-plan` (coaching brief and record);
  - `opening-check` (your moves against theory, with scores);
  - `status`.

**Marketplace**

- `.claude-plugin/marketplace.json` at the repository root makes the checkout
  installable with `claude plugin marketplace add <repo>` and
  `claude plugin install chessgraph@chessgraph`.

**New commands**

- `uv run chessgraph-status` (`chess_mcp/status.py`) prints whether
  PostgreSQL, Neo4j and Stockfish are reachable, with counts. It only reads,
  never prints the account name, and reports a down service as `DOWN` without
  showing the exception text.
- `uv run chessgraph-smoke` (`chess_mcp/smoke.py`) starts each MCP server over
  stdio with the official MCP client, the way a host does. It compares each
  tool list with the expected contract and calls one cheap tool per server.
  No model or API key is involved.

**Removed**

- `agent/`: `SOUL.md`, `MEMORY.md`, `USER.md`, `README.md` and
  `hermes-mcp.example.yaml`.
- `AGENTS.md` was renamed to `CLAUDE.md` and rewritten for Claude Code. The
  player facts from the memory seeds moved there, without the account name.

**Docs**

- `README.md` has a new step 4, "Install the Claude Code plugin". The
  architecture diagram, the sequence diagram and the scope now name Claude.
- New `docs/plugin.md` covers the layout, install, server launch, testing
  without a model, and ideas for later.
- Hermes host text was removed from `docs/mcp.md`, `chess_mcp/README.md`,
  `chess_mcp/stockfish/README.md`, `backend/README.md` and `backend/main.py`.

**Not yet changed (Batch 3)**

- The UI coach panel still posts to the `/hermes-api` Vite proxy.

### Tested

| Command | Result |
| --- | --- |
| `claude plugin validate --strict plugins/chessgraph` | passed. One plugin-directory advisory remains: no icon, which only matters for catalog submission. |
| `claude plugin validate --strict .` (marketplace) | passed |
| Isolated install with `CLAUDE_CONFIG_DIR` set to a throwaway folder: `marketplace add`, `install`, `configure --values-stdin`, then `claude plugin details` | 5 skills, 1 agent, 3 MCP servers, about 392 always-on tokens |
| `claude mcp list` from `/tmp` in that isolated config | `plugin:chessgraph:postgres`, `neo4j` and `stockfish` all **Connected**, confirming `${user_config.chessgraph_home}` substitution |
| `uv run chessgraph-status` | postgres 4,595 games / 388,522 moves (all evaluated); neo4j Position 360,182, Game 4,595, Opening 3,704, EndgamePattern 848; Stockfish 17.1 |
| `uv run chessgraph-smoke` | PASS for all three servers (9, 6 and 3 tools); `validate_line` returned e4 e5 Nf3 |
| `uv run pytest` | 80 passed, 3 skipped |
| Integration tests | 3 passed |
| Account-name scan over the staged files | no match |

New tests in `tests/test_status_and_smoke.py`:

- a failing service is reported without leaking the exception text;
- the rendered status format;
- the smoke contract equals each server's registered tools;
- smoke summaries never include the username;
- the JSON fallback parser;
- unknown server names are rejected.

## Batch 3: in-app coach on the Claude API, with an offline mode

### Why

- The UI coach posted to a Hermes gateway that was never running.
- The coach now lives inside the retrieval API and talks to Claude directly.
- With no API key it still answers, from the same tools and with no model, so
  everything can be tested today.

### Changed

**Backend: `backend/coach/`**

- **`tools.py`** has twelve tools mirroring the MCP contracts:
  - PostgreSQL: `get_player_summary`, `get_coaching_brief`, `list_games`,
    `get_game_moves`, `get_blunders`, `find_position_occurrences`,
    `lookup_opening`
  - Neo4j: `get_position_context`, `get_position_moves`
  - Stockfish: `analyze_position`, `compare_move`, `validate_line`

  They run in-process on the existing repositories.
  - Inputs are validated with Pydantic, and unknown fields are rejected.
  - Limits are tighter than the MCP limits.
  - The player is never a tool argument.
  - Every result is redacted: the account in `CHESS_USERNAME` becomes `you`
    and every other username becomes `opponent`, including inside free text
    such as `termination`. No player name is sent to Anthropic.
  - A failing store becomes an `is_error` tool result ("neo4j is
    unavailable"), not a crash.
- **`prompt.py`** holds a fixed system prompt (persona, evidence rules, answer
  shape, `PLAY:` line) and the user turn built from the board context and up to
  12 history turns.
- **`providers.py`**:
  - `ClaudeProvider` runs a manual streamed tool loop with
    `client.messages.stream`:
    - model `CLAUDE_MODEL` (default `claude-opus-5-5`);
    - `output_config.effort` from `CLAUDE_EFFORT` (default `low`);
    - automatic prompt caching (`cache_control`);
    - server-side refusal fallback (`fallbacks: "default"`, beta
      `server-side-fallback-2026-07-01`), which `CLAUDE_REFUSAL_FALLBACK=off`
      disables;
    - at most 8 tool rounds, with all tool results returned in one user
      message;
    - handling for `refusal`, `pause_turn` and `max_tokens`;
    - API errors mapped to messages that never echo the key.
    - Tools are sent without `strict` and without eager input streaming. Their
      inputs are a few short fields, and Pydantic validates every call before
      it runs. That avoids schema features that cannot be checked without a
      key.
  - `OfflineProvider` runs a fixed plan of the same tools:
    - a position question gets `analyze_position` and `get_position_moves`;
    - a training question gets `get_coaching_brief`;
    - a game question gets `get_blunders` and `compare_move`.

    It renders the results as text labelled "Offline evidence mode". Losses of
    5,000 cp or more are described as mate swings, because stored mate scores
    are flattened to ±10000.
- **Selection:** `provider_from_settings()` picks Claude when
  `ANTHROPIC_API_KEY` is set and offline otherwise. `COACH_MODE` forces either
  mode.

**API**

- `POST /api/coach/chat` streams the answer as server-sent events: `start`,
  `tool_start`, `tool_end`, `text`, `done`, `error`.
- `GET /api/coach/status` returns `{"mode": ..., "model": ...}`.

**UI**

- The `/hermes-api` proxy is gone from `vite.config.ts`. `/api` gets a 300 s
  timeout for long answers.
- `services/coach.ts` is rewritten. It streams Server-Sent Events from
  `/api/coach/chat` through an incremental parser, sends `game_id`, the profile
  and a short history, and caches answers with their mode. Error messages are
  specific: unreachable API (with the start command), a down store, an empty
  answer, a timeout.
- `useCoach` shows the answer as it streams (a pending message) and exposes the
  evidence `trace` and the `mode`.
- `CoachPanel`:
  - The Games, Graph and Stockfish chips now reflect real tool calls: `done` in
    green, `failed` struck through. They used to be cosmetic.
  - A header badge shows Claude or Offline evidence.
  - Line breaks in answers are kept.
- Hermes labels were removed from the views and the graph tooltip. The review
  coach now sends the game id, so "Why did I lose?" reads that game's mistakes.

**Configuration**

- `.env.template` replaces `HERMES_*` with `ANTHROPIC_API_KEY` (empty),
  `COACH_MODE`, `CLAUDE_MODEL`, `CLAUDE_EFFORT` and `CLAUDE_REFUSAL_FALLBACK`.
  The old `HERMES_*` lines in a local `.env` are now unused.
- New dependency: `anthropic` (2.12).
- New `.claude/launch.json` starts the `api` and `ui` dev servers for preview.

### Found, not fixed here

- **The My games tab blanks the whole app when the browser has no WebGL.** The
  3D graph (`react-force-graph-3d`) throws, and no error boundary catches it.
  This was seen in the sandboxed preview browser. Batch 5 replaces that graph.

### Tested

| Command | Result |
| --- | --- |
| `uv run pytest` | 113 passed, 3 skipped |
| `CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py` | 3 passed |
| `cd ui && npm test` | 72 passed |
| `cd ui && npm run lint` | 0 errors; the same 3 existing warnings |
| `cd ui && npm run build` | built |
| Live offline coach on the real databases (FastAPI `TestClient`) | Position: `EVAL +0.57`, `MOVE e4`, the line, and the graph move counts. Training: strength Vienna Game (8 games), target Bird Opening (21 games), four tasks. Game review: the largest mistakes and a fresh `compare_move`. |
| Browser, Training tab | "What should I play here?" streamed an offline answer. The Graph and Stockfish chips turned green. The board animated the `PLAY` line. "What should I train?" lit only the Games chip. |
| `curl -N` through the Vite proxy (`/api/coach/chat`, review question) | Events arrived one by one: `start`, `tool_start`/`tool_end` for `get_blunders` and `compare_move`, `text`, `done` |

New tests:

- `tests/test_coach.py` (33 tests, with a scripted fake Anthropic client and no
  network):
  - Claude loop:
    - two parallel tools are answered in one message;
    - request parameters: model, system prompt, effort, cache control,
      fallback beta, tool order;
    - the plain endpoint is used when the fallback is off;
    - invalid input and a down store become `is_error` results;
    - the iteration cap;
    - refusal;
    - `pause_turn`;
    - API errors are mapped without leaking the key;
    - the account name never appears in what is sent.
  - Offline answers: position, Neo4j down, training, game review, played move,
    mate formatting, mate-swing losses.
  - Redaction, tool definitions (closed, untitled, stable order), the history
    merge, the SSE route and its validation, provider selection, and the
    question classifier.
- `ui/src/services/coach.test.ts` (14 tests):
  - pending messages are never stored;
  - the SSE parser handles partial chunks, CRLF line endings and bad JSON;
  - history trimming;
  - the request body, with no key or authorization header;
  - streaming text, trace and phases from a stream split mid-event;
  - cache replay with its mode;
  - error event, 503 body, unreachable API, empty answer.

## Batch 4: Stockfish backfill fix, read indexes, Neo4j graph v2

### Why

- The Stockfish backfill re-parsed PGN and, on a game it could not parse,
  `break`-ed out of the move loop with the game still unevaluated, so the next
  batch selected the same game again, forever.
- The v1 graph mixed things up:
  - `PLAYED_MOVE` merged your moves with your opponents' moves and scored both
    from your side;
  - `visit_count` was overwritten on one path and double-counted on reruns;
  - `Position.eval_cp` mixed two sign conventions;
  - `material_sig` put the side with more material first, while the Endgame
    Atlas types put White first, so no game position ever linked to an
    Atlas hub;
  - `best_move_uci` was `MAX()` of the candidates, an opening's `eco_code` was
    whichever line was written last, and nothing tied a game to the positions
    it went through.

### Changed

**PostgreSQL (ETL only)**

- `etl/postgres_db/load_stockfish_eval.py` is rewritten:
  - it replays the stored `uci_move` values instead of re-parsing PGN;
  - `evaluate_moves()` is pure: N + 1 searches for N plies (the score after
    move *n* is the score before move *n + 1*), stored from the mover's side
    with the existing convention (`cp_loss = max(0, before - after)`, mate
    flattened to +/-10000);
  - a game whose moves do not replay, or whose plies are not contiguous, is
    logged and skipped for the rest of the run, so the loop always ends;
  - each game is written in one transaction.
- `etl/sql_files/migrations/001_read_indexes.sql` adds three indexes (no data
  change): `game_moves(fen_after_norm)`, `lower(white_username)`,
  `lower(black_username)`. They serve the position and player filters the
  MCP tools already run. Applied to the local database after Junior approved.

**Neo4j graph v2 (`etl/neo4j_db/`)**

- The three v1 loaders are replaced by:
  - `transform.py`: pure functions from PostgreSQL rows to graph rows
    (`build_graph`), unit-tested without a database;
  - `write.py`: batched `execute_write` statements, schema, `label_counts`,
    and `reset_chess_graph`, which detach-deletes only the chess labels
    with `CALL (n) { DETACH DELETE n } IN TRANSACTIONS`;
  - `neo4j_load.py`: `--dry-run` (transform and print counts) and `--reset`.
    It compares every non-chess label count before and after and exits with
    status 2 if one changed.
- Schema v2 (full table in `etl/neo4j_db/neo4j_init.md` and the
  `chessgraph-neo4j://schema` resource):
  - `Position` gains `phase` (simplified Lichess divider), `is_theory`,
    `visit_games` (distinct games), `eval_cp` from the side to move with
    `eval_samples`, the most frequent stored `best_move_uci` and its SAN;
    `material_sig` is White first in Atlas order. `last_moved_piece` and
    `last_move_san` are gone.
  - `PLAYED_MOVE` is keyed by `(uci_move, by)` with `by` = `owner` or
    `opponent`; results, `score_pct` and `avg_eval_after` are from the mover's
    side; it adds `games` (distinct), `times`, severity counts and
    `is_engine_best`.
  - `THEORY_MOVE` keeps every ECO code in `eco_codes`.
  - New: `Player`, `OpeningFamily`, `ChessGraphMeta`, `PLAYED_AS`, `REACHED`,
    `OPENED_WITH`, `LEFT_THEORY_AT`, `ENTERED_ENDGAME`, `ENGINE_BEST`,
    `IN_OPENING`, `IN_FAMILY`.
  - `BLUNDERED_IN` becomes `MISTAKE_IN` with `severity` (inaccuracy 50,
    mistake 100, blunder 300 cp), `mate_swing` and `best_uci`, for the owner's
    moves only.
  - Game positions of six pieces or fewer link to Atlas hubs
    (`HAS_ENDGAME_TYPE {from_games: true}`); Atlas samples keep
    `{benchmark: true}`.
  - No clock fields: the stored PGN has no `%clk` comments.
- Severity thresholds live once, in `chess_mcp/chess.py`
  (`SEVERITY_MIN_CP`, `severity_for`), for the ETL and the tools.

**Read side**

- `chess_mcp/neo4j/` (repository, models, server) moves to schema v2:
  - `get_position_context` adds phase, opening families, the number of theory
    lines through the position and the engine best move;
  - `get_position_moves` takes `by` (`all`, `theory`, `owner`, `opponent`)
    and returns the position and its engine best move with the moves;
  - `get_game_blunders` and `get_recurring_blunder_positions` take
    `min_severity`; the recurring count is now distinct games;
  - `find_transpositions` keeps one path per move sequence and counts distinct
    predecessor positions, since a played move now has two edges;
  - new tools `get_games_through_position` and `get_theory_exits`
    (eight tools in all). The planned `get_opening_tree` was dropped: it is
    `get_position_moves` with `by`;
  - `get_position_moves` lists the most-played moves first, then book moves
    ranked by how many ECO lines use them. Book-first ordering let the ~20 book
    first moves fill the limit, so the offline coach told you the start
    position was "not in your stored games" (you moved from it in 2,305);
  - `get_theory_exits` flags `book_ended` when the opening data has no move
    from the exit position (616 of 4,586 exits): the line ran out, it was not
    left.
- `normalize_fen` rebuilds the key with python-chess, so an en-passant square
  with no legal capture (`... b KQkq e3` after 1.e4) is dropped the way the
  ETL stores it. Before, such a FEN from a client missed the stored position.
- The in-app coach gains `get_games_through_position` and `get_theory_exits`
  (14 tools) and `get_position_moves` takes `by`. The offline position answer
  makes two filtered reads (`by="owner"`, `by="theory"`) and counts only your
  own moves as "your games".
- `chessgraph-smoke` expects the eight Neo4j tools.
- Plugin skills: `opening-check` starts from `get_theory_exits` and splits
  moves by mover; `review-game` uses `get_games_through_position` and no longer
  asks for clocks; `training-plan` adds recurring mistake positions.

**Docs**: `etl/neo4j_db/neo4j_init.md` (load, schema v2, rules, verification
queries), `chess_mcp/neo4j/README.md`, `docs/mcp.md`, `etl/README.md`,
`README.md`, `data/README.md` (no clock data).

### Tested

| Command | Result |
| --- | --- |
| `uv run pytest` | 167 passed, 4 skipped (the opt-in integration tests) |
| `CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py` | 4 passed, including the new v2 check against the loaded graph |
| `uv run chessgraph-smoke` | postgres 9 tools, neo4j 8 tools, stockfish 3 tools: all PASS |
| `uv run chessgraph-status` | 4,595 games, 388,522 moves (all evaluated); Position 360,182, Game 4,595, Opening 3,704, EndgamePattern 589; Stockfish 17.1 |
| `claude plugin validate --strict plugins/chessgraph` | Validation passed |
| `cd ui && npm test` | 72 passed (no UI change in this batch) |
| `psql -f etl/sql_files/migrations/001_read_indexes.sql` | 3 × `CREATE INDEX`; the three indexes are listed in `pg_indexes` |
| `uv run python etl/neo4j_db/neo4j_load.py --dry-run` | 35 s; row counts below |
| `uv run python etl/neo4j_db/neo4j_load.py --reset` | exit 0 in about 3 minutes; "Non-chess labels unchanged (26 labels checked)" |
| Live call of every graph tool | 4–260 ms each, `find_transpositions` up to depth 4 included |
| Offline coach through `POST /api/coach/chat` on live stores | "you moved from here in 2305 games; most often d4 (1843 games, …)", book moves d4, e4, c4 |
| Account-name scan of every changed file | no match |

Before the reset, no node carried both a chess label and a non-chess label and
no relationship ran from the chess graph to another project's nodes.

Live graph after the load (each equals the dry-run row count):

| Nodes | Count | Relationships | Count |
| --- | ---: | --- | ---: |
| Position | 360,182 | PLAYED_MOVE (owner 174,250, opponent 175,239) | 349,489 |
| Game | 4,595 | REACHED (= 388,522 moves + 4,595 starts) | 393,117 |
| Player (1 owner) | 3,959 | ENGINE_BEST | 130,894 |
| Opening | 3,704 | MISTAKE_IN (22,262 / 19,301 / 7,695 by severity) | 49,258 |
| OpeningFamily | 146 | IN_OPENING | 31,978 |
| EndgamePattern | 589 | HAS_ENDGAME_TYPE (12,450 from games, to 297 hubs) | 19,555 |
| ChessGraphMeta | 1 | THEORY_MOVE | 7,819 |
| | | PLAYED_AS | 9,190 |
| | | OPENED_WITH / LEFT_THEORY_AT / ENTERED_ENDGAME | 4,595 / 4,586 / 3,643 |

v1 had 848 `EndgamePattern` nodes, because game positions created extra hubs
under the wrong orientation; v2 has the 589 Atlas types, and 12,450 game
positions link to them (v1: none). No `BLUNDERED_IN`, `visit_count` or
`last_move_san` remains.

New tests:

- `tests/test_graph_transform.py` (30): material signature in Atlas order,
  phase rule, severity, rating bands, legal replay, and `build_graph` on three
  synthetic games: REACHED count, moves split and scored by mover, eval from
  the side to move, ECO codes, game milestones, owner-only mistakes, engine
  best edges, canonical players, game properties, opening families, endgame
  links, deterministic reruns.
- `tests/test_graph_write.py` (7, fake driver): every payload list has a write
  step, statements name only chess labels and never delete, the reset touches
  only chess labels, batching, flat meta properties, the non-chess label guard.
- `tests/test_stockfish_eval_loader.py` (6): mover-side signs with N + 1
  searches, unknown scores, ReplayError, game-over scoring without a search,
  and the skip list ending the loop (in-memory SQLite).
- Updated: `test_neo4j_repository.py` (v2 rows, filters, severity, new tools,
  null `eco_codes`, en-passant key, move ordering), `test_neo4j_server.py`
  (eight tools, schema text, delegation), `test_coach.py` (14 tools, mover
  filter, offline answers), `test_chess.py` (en-passant key).

### Found, not fixed here

- `ruff` is not a project dependency, so no Python lint ran.

## Batch 5: play-first UI

### Why

- The board shared the screen with three panels and was squeezed.
- Playing Stockfish paused after every engine move and fired a coach request;
  there was no strength setting, no move list, no takeback and no PGN.
- The 3D graph blanked the whole My games view without WebGL, and the review's
  previous/next buttons jumped back into the game while a Stockfish line was
  shown.
- The clock kept running in a hidden view, and player bars said "Junior"
  whatever the account was.

### Changed

**API**

- `POST /api/engine/play` (`backend/opponent.py`): one opponent move with
  `UCI_LimitStrength`/`UCI_Elo` (1320–3190, `null` = full strength) and a
  50–3000 ms think time. It runs in its own Stockfish process, so the analysis
  engine always searches at full strength. Answers the move, SAN, FEN and the
  score from the mover's side (used to let a lost engine resign).
- `GET /api/explorer`: graph v2 context, moves (book, yours, opponents') and
  your games through the position. A position missing from the graph is an
  empty answer, not a 404.
- A dead Stockfish process answers 503 instead of 500.

**UI layout**

- Board first: the board column is sized to the window height (612 px at
  1440×900, no page scroll), with one tabbed side panel. On a phone the panel
  moves under the board.
- Player bars show name, rating, clock, captured pieces and the material lead,
  and highlight the side to move. The name comes from `GET /api/player`.
- The board highlights a king in check, keeps legal-move dots, and lets you
  draw your own arrows with a right-click drag. The evaluation bar animates.
- Move sounds (move, capture, check, castle, end) are synthesized with
  WebAudio, with a mute button remembered in the browser.
- ← → step through moves, ↑/Home and ↓/End jump, F flips, in every board view.

**Play & train** (was Training)

- Tabs: Play, Moves, Coach, Explorer.
- New game: colour, strength (matched to your average rating until you choose)
  and time control. The engine answers continuously; the coach is asked only
  when you press Explain or ask a question.
- Takeback (your move and its reply), Resign, Rematch, Switch sides, Copy PGN.
- Browse earlier moves without leaving the game; moving returns to the live
  position.
- Leaving the view pauses a running clock.
- A coach answer's line is drawn as arrows instead of being played onto your
  game.

**My games**

- Tabs: Games, Moves, Coach, Explorer. The 3D position graph and its
  dependencies (`react-force-graph-3d`, `three`, `three-spritetext`,
  `@types/three`) are removed; the page no longer needs WebGL.
- Numbered move table with `?!`, `?` and `??` from stored centipawn loss
  (50/100/300, as in the graph), the key move underlined, and each side's
  mistake count.
- Previous/next work on whatever is shown: the game, or the Stockfish line.
- A loss of 5,000 cp or more reads "swings to a mate", as in the coach.
  The UI used 9,000, so an 8,990 cp swing was shown as a plain loss.
- The Explorer can open any game that reached the position, even one not yet
  loaded in a folder.

**Docs**: `README.md` (routes, the three modes), `ui/README.md`,
`backend/README.md`. Both READMEs still said the coach had twelve tools; it has
fourteen since Batch 4.

### Tested

| Command | Result |
| --- | --- |
| `uv run pytest` | 175 passed, 5 skipped (the opt-in integration tests) |
| `CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py` | 5 passed, including a live 1320-Elo move |
| `uv run chessgraph-smoke` | postgres, neo4j, stockfish: all PASS |
| `cd ui && npm test` | 93 passed (72 before) |
| `cd ui && npm run lint` | 2 warnings, both existing (`usePositionEval`, `RecapView`); the `GamesView` one is gone |
| `cd ui && npm run build` | built; Vite still warns that the main chunk is over 500 kB |
| Account-name scan of every changed file | no match |

In the browser (in-app preview, API restarted on the new code):

- 1440×900: the page is exactly 900 px tall, the board column has no overflow.
  A game as White at 1800: 1.e4 c6 2.d4 d5 came back at once, the clocks ran,
  ← ← showed move 2, End returned, Takeback restored 1.e4 c6 with White to
  move. The Explorer showed the Caro-Kann (B10), 462 of your games, 216 W, 30
  D, 216 L, with 2.d4 marked book and engine best.
- Switching to My games paused the running game clock. The latest game opened
  at its key moment with arrows; the move table showed 14 glyphs (2 of your
  mistakes, 7 of the opponent's). After *Better move*, previous/next stepped
  through the line (11. Rh4# → 10. Kh1 → 9. Bc5+ → 10. Kh1).
- 375×812: no horizontal scroll, a 327 px board, tabs under the board.
- A fresh load visiting every view and tab: no console error, and no
  three.js request.
- Two layout bugs were found and fixed during this check: visually hidden
  labels in the lesson list stretched the page to 1,482 px, and the board
  column was 17 px too tall.

New tests:

- `tests/test_opponent.py` (8): UCI options for limited and full strength, the
  score from the mover's side, refused requests never reach the engine, an
  illegal engine move, the play route's validation, the explorer route with a
  known and an unknown position.
- `ui/src/lib/*.test.ts`: notation (glyphs, move pairing including a
  Black-first start, PGN), material (captures, lead, promotion), strength
  (range, closest level, think time), keys (navigation, flip, typing targets),
  explorer (row merge and order), sounds, and `checkedKingSquare`.

### Not done

- No visual regression test: the browser checks above were run by hand.

## Batch 6: the coach runs on the Claude Code login, not an API key

Branch `feat/subscription-coach`.

### Why

- The coach needed a paid `ANTHROPIC_API_KEY`. Without one, the UI only had the
  offline template.
- The Claude subscription is already logged in for Claude Code. The Claude
  Agent SDK can run the coach through that login, with the same tools.

### Changed

- `pyproject.toml`: `claude-agent-sdk>=0.2.189` replaces `anthropic`. The SDK
  bundles the Claude Code CLI.
- `backend/coach/providers.py`: `ClaudeProvider` now runs
  `claude_agent_sdk.query`. Its `run` is an async generator.
  - It uses `claude-opus-5-5` at effort `low` (`CLAUDE_MODEL`, `CLAUDE_EFFORT`)
    and the coach system prompt, which replaces Claude Code's own.
  - Isolation: `tools=[]` (no Bash, Read and so on), `setting_sources=[]` (no
    user or project settings, hooks or CLAUDE.md) and `strict_mcp_config=True`.
    Only the fourteen coach tools are offered, through an in-process MCP server
    (`mcp__coach__*`).
  - Each tool still goes through `run_tool`: Pydantic validation, then
    username redaction. One lock serializes the calls, because a single
    Stockfish process serves the coach.
  - The SSE events are unchanged (`start`, `tool_start`, `tool_end`, `text`,
    `done`, `error`), so the UI did not change. Text streams from the SDK's
    partial messages.
  - Errors become safe messages: a missing login says to run `claude` and
    `/login`; a missing CLI, a refusal and the turn cap (`max_turns`, 8) each
    have their own message. stderr and the prompt are never shown.
  - Removed: the Messages API loop, `api_error_message`, the refusal-fallback
    beta, prompt caching parameters.
- `backend/coach/prompt.py`: `prompt_text` replaces `conversation`. Earlier
  turns go in as text before the board context, because each question is one
  `query`.
- `backend/coach/__init__.py`: `COACH_MODE` is `claude` (default) or
  `offline`. `ANTHROPIC_API_KEY` and `CLAUDE_REFUSAL_FALLBACK` are gone.
- `backend/main.py`: `/api/coach/chat` streams both sync providers (offline)
  and async providers (Claude).
- `.env.template`: the coach block now describes the login, and notes that it
  is for personal, local use only.
- `ui/src/services/coach.ts`: doc comment only. `coach.test.ts`: the error
  fixture is the login message.

### Checks

| Command | Result |
| :--- | :--- |
| `uv run pytest` | 174 passed, 5 skipped (the opt-in integration tests) |
| `cd ui && npm test` | 93 passed |
| `cd ui && npm run build` | built; same chunk-size warning as before |
| `curl -N POST /api/coach/chat` (start position, live stores, your login) | `start` → `get_coaching_brief` (postgres) → `get_position_moves` (neo4j) → `analyze_position` (stockfish) → text → `done`, in 10.7 s; model `claude-opus-5-5` |
| Account-name scan of that SSE stream | no match |
| SDK probe: init message | model `claude-opus-5-5`, tools only `mcp__coach__*`, `apiKeySource: none` (the subscription login) |

In the browser (in-app preview, 1440×900): on Play & train, Coach tab, "Who is
better here and what is the plan?" got a Claude answer with the Games, Graph
and Stockfish chips lit and the recommended 1.d4 drawn on the board.

New and rewritten tests in `tests/test_coach.py`: a scripted fake `query` calls
the real tool handlers. They cover event order and tool sources, redaction of
tool results, the session options (model, effort, no built-in tools, no
settings, only coach tools), invalid input and a down store as `is_error`
results, the turn cap, a refusal, a missing login, CLI and process errors
without stderr, `prompt_text`, the mode settings, and the async SSE route.

### Not done

- The README still describes the API key. That is batch 8.

## Batch 7: graph context for the coach (GraphRAG), and graph invariants

### Why

- **The graph is reliable.** A read-only audit compared Neo4j with
  PostgreSQL. Every check agreed:
  - 4,595 games;
  - REACHED = 388,522 moves + 4,595 starts;
  - PLAYED_MOVE `times` summed by mover = 194,423 owner and 194,099 opponent
    moves, the same as PostgreSQL;
  - wins + draws + losses = games on every edge;
  - MISTAKE_IN = 22,262 inaccuracies, 19,301 mistakes and 7,695 blunders, the
    same as PostgreSQL;
  - no stale edge, no orphan position, and exactly one owner Player.
- **Two gaps are known and by design.**
  - MISTAKE_IN is stored per ply: 49,258 edges for 49,147 distinct game and
    position pairs, because repetitions are not collapsed.
  - No ENTERED_ENDGAME position links to an Endgame Atlas pattern. The Atlas
    only covers 6 pieces or fewer, and the first endgame position always has
    more.
- **So the graph is grounded evidence of the player's style.** It records
  which moves you choose, how you score with them, and where you go wrong,
  position by position, transpositions included.
- **Pre-fetching it is cheaper.** Through Claude Code, every tool round is a
  full Opus turn. Before this batch, a position question spent 2 to 4 rounds
  on graph tools. "Mistakes near this position" was not reachable from the
  in-app coach at all.
- **It is retrieval by key, with no embeddings.** It is a lookup by
  `fen_norm` plus a bounded walk, so no vector search is needed.

### Changed

- `chess_mcp/neo4j/repository.py`: `get_style_context(fen, depth=2, limit=5)`,
  a single read transaction. It returns:
  - your moves, opponents' moves and book moves from the position;
  - the exact opening and its families;
  - your record from the position, with your latest games through it;
  - the positions within `depth` plies along played moves where you made
    stored mistakes, ranked by the number of games.

  `depth` is clamped to `NEO4J_MAX_PATH_DEPTH` (at most 4) and checked against
  the 1..4 whitelist before it is spliced into the query. `limit` goes through
  `clamp_limit`. A position missing from the graph returns an empty context.
- `chess_mcp/neo4j/models.py`: `StyleContext`, `NearbyMistake`.
- `backend/coach/tools.py`: `graph_context(fen, ctx)` turns the result into
  compact JSON. Usernames are redacted. The output is capped at 6,000
  characters by dropping nearby mistakes, then recent games, then opponent
  moves. It returns `None` when Neo4j fails.
- `backend/coach/providers.py`: before Claude reads the question,
  `ClaudeProvider` fetches the graph context, reported as
  `get_style_context` on the Graph chip, and adds it to the prompt. An
  explanation of a move just played skips it.
- `backend/coach/prompt.py`: `user_turn` and `prompt_text` take the block.
  The system prompt gains one rule: cite the graph context rather than
  re-reading the same position with tools.

### Checks

| Command | Result |
| :--- | :--- |
| `uv run pytest` | 181 passed, 7 skipped (the opt-in integration tests) |
| `CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py` | 7 passed, including the two new tests |
| `PROFILE` of the nearby-mistakes walk | from the start position, 3,129 db hits at depth 2 and 16,851 at depth 4; after 1.e4 or 1.d4, under 0.05 s |
| `get_style_context` live | start position: 1.19 s cold, 19,829 characters raw; after 1.d4: 0.07 s; an unknown endgame position: empty |
| `curl -N POST /api/coach/chat` after 1.d4 | `get_style_context` (neo4j) → `analyze_position` (stockfish) → answer → `done` in 8.4 s. The answer cites your 1...d5 record (480 games) and a nearby repeated mistake (2...Nf6 against 2.c4, 18 games, 54 cp) |
| Account-name scan of that SSE stream | no match |

New tests:

- `tests/test_neo4j_repository.py` (3): one read session on the configured
  database with no write keyword, the FEN normalized, depth clamped to
  `*0..4`, limit clamped to 100, rows flattened into the model; an unknown
  position gives an empty context; a depth below 1 is refused.
- `tests/test_coach.py` (4): the context is fetched first and its JSON is in
  the prompt; it is skipped when Neo4j is down; it is skipped for a played-move
  explanation; it is redacted and bounded, and trimmed from the end.
- `tests/test_integration.py` (2):
  - `test_neo4j_graph_agrees_with_postgres` turns the audit into assertions:
    game count, REACHED = moves + games, PLAYED_MOVE `times` by mover,
    W + D + L = games, MISTAKE_IN by severity, one owner.
  - `get_style_context` from the start position.
