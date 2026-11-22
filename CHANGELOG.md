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
