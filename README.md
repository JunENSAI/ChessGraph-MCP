<div align="center">

# ChessGraph MCP

### A local layer for personalized chess coaching

Connect an MCP-capable agent to personal game history, a positional knowledge
graph, and reproducible Stockfish analysis—without giving the model unrestricted
database access.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/Model_Context_Protocol-2.3%2B-6C5CE7)](https://modelcontextprotocol.io/)
[![Stockfish](https://img.shields.io/badge/Stockfish-UCI-4B8BBE)](https://stockfishchess.org/)
[![License](https://img.shields.io/badge/License-MIT-2EA44F)](LICENSE)

**Deterministic analysis · Personal evidence · Typed MCP tools · Read-only by design**

</div>

---

## Why ChessGraph?

A chess engine can calculate excellent moves, but it does not know your history.
A database can reveal recurring mistakes, but it cannot calculate the best move
in a new position. A language model can explain ideas, but it should not invent
the chess evidence behind them.

ChessGraph MCP separates those responsibilities:

- **Stockfish calculates** candidate moves, evaluations, WDL, and principal variations.

- **PostgreSQL remembers** games, move telemetry, openings, endgames, and historical engine evaluations.

- **Neo4j connects** positions, personal moves, theory moves, transpositions, games, and endgame patterns.

- **The retrieval API serves** those same reads to the interface, without asking the model to fetch the page.

- **Claude explains** the combined evidence as a personalized lesson, through the
  `chessgraph` Claude Code plugin.

> The design principle is simple: **the engine searches, deterministic code
> validates, the databases provide context, and the model explains only the
> evidence it receives.**

## Architecture

```mermaid
flowchart LR
    subgraph sources [Data sources]
        pgn["Chess.com PGN archives"]
        openings["Lichess opening theory"]
        endgames["Endgame Atlas benchmarks"]
    end

    subgraph ingestion [Deterministic ingestion]
        normalizer["ETL and FEN normalization"]
        backfill["Historical Stockfish backfill"]
        graphSync["PostgreSQL to Neo4j sync"]
    end

    subgraph knowledge [Local evidence stores]
        postgres[("PostgreSQL: games and telemetry")]
        neo4j[("Neo4j: position graph")]
    end

    subgraph runtime [Read paths]
        api["FastAPI retrieval + in-app coach"]
        pgMcp["PostgreSQL MCP: 9 tools"]
        graphMcp["Neo4j MCP: 6 tools"]
        sfMcp["Stockfish MCP: 3 tools"]
        stockfish["Stockfish UCI"]
    end

    ui["React coach"]
    host["Claude Code + chessgraph plugin"]
    coach["Evidence-backed coaching response"]

    pgn --> normalizer
    openings --> normalizer
    endgames --> normalizer
    normalizer --> postgres
    postgres -->|"unevaluated moves"| backfill
    backfill -->|"scores and CPL"| postgres
    postgres --> graphSync
    graphSync --> neo4j

    ui -->|"page facts"| api
    ui -->|"questions (SSE)"| api
    api -->|"tool loop"| claudeApi["Claude API"]
    api -->|"repository reads"| postgres
    api -->|"repository reads"| neo4j
    api -->|"bounded search"| stockfish
    host -->|"typed MCP calls"| pgMcp
    host -->|"typed MCP calls"| graphMcp
    host -->|"typed MCP calls"| sfMcp
    pgMcp -->|"parameterized reads"| postgres
    graphMcp -->|"bounded traversals"| neo4j
    sfMcp -->|"serialized UCI"| stockfish
    host --> coach
```

The ETL layer writes data. The MCP servers and the retrieval API only read.
They call the same repositories in `chess_mcp/`. MCP tools stay typed and
bounded for Claude. The API serves the facts the interface can draw before a
question is asked, such as the rating-band recap and the ranked training plan.
Claude explains; it does not assemble the page.

## What the agent can ask

| Evidence source | Best suited for | MCP capabilities |
| --- | --- | --- |
| PostgreSQL | Game selection, longitudinal statistics, move records, openings, endgames, ranked coaching briefs | 9 curated tools, paginated move retrieval, statement timeouts |
| Neo4j | Theory versus personal choices, transpositions, recurring positions, graph context | 6 curated tools, anchored queries, maximum traversal depth |
| Stockfish | Fresh position analysis, candidate comparison, WDL, legal variations | MultiPV, same-root move comparison, line validation |

Examples:

- “Show my largest rapid-game mistakes and explain the top three.”

- “Where did I leave opening theory, and what did I usually play instead?”

- “Do different move orders in my games transpose into this position?”

- “Compare my move with Stockfish's best move using the same search budget.”

- “Which opening family scores worst for me, and what should I drill first?”

- “Which positions keep tempting me into the same wrong move?”

- “Which endgame patterns recur in my losses?”

## Evidence flow for a coaching answer

```mermaid
sequenceDiagram
    actor User
    participant Coach as Claude (chess-coach)
    participant PG as PostgreSQL MCP
    participant Graph as Neo4j MCP
    participant SF as Stockfish MCP

    User->>Coach: Why was this move a mistake?
    Coach->>PG: get_game_moves and get_blunders
    PG-->>Coach: FEN, played move, CPL, clock, game context
    Coach->>Graph: get_position_context and get_position_moves
    Graph-->>Coach: Theory, personal choices, recurring patterns
    Coach->>SF: compare_move from the same root
    SF-->>Coach: Best line, played line, score, WDL, provenance
    Coach->>SF: validate_line for any cited continuation
    SF-->>Coach: Legal UCI, SAN, and resulting FENs
    Coach-->>User: Verified explanation and actionable lesson
```

## Personalized training

The training view is not a fixed lesson list. Both API endpoints behind it read
the stored games and rank what to work on next.

`GET /api/coach/brief` returns the material a coach would open with:

- the **strongest** opening families, by score in the stored games;
- the **target**: the weakest opening family, with its wins, draws and losses;
- **calculation** positions — repeated spots where the recorded move differs
  from `best_move_uci`, ranked by frequency and average centipawn loss;
- the **endgames** field, which states plainly that endgame type is not stored
  on games rather than guessing one;
- four **tasks**, each with a reason that quotes the stored record.

`GET /api/coach/plan` returns up to six ranked `PlanItem`s. Each item carries a
`kind` (`opening`, `defense`, `endgame` or `puzzle`), the `reason` that justifies
it, a `goal`, a `check_after_games` review point, the line to drill, the player's
colour, and a `ready` flag.

A drill is only offered when it can actually be drilled: `ready` stays `false`
until the stored theory line for that family is at least `MIN_DRILL_PLIES` (6)
plies long, and the reason says how many plies it has. Drilled lines are capped
at `TASK_PLIES` (12). The interface shows the drill length next to the board, so
a short line is reported as short instead of silently passed off as a lesson.

## Design guarantees

### Read-only agent access

- No arbitrary SQL or Cypher tools.

- PostgreSQL uses parameterized statements, read-only transactions, local
  statement timeouts, and result caps.

- Neo4j uses read transactions, parameterized values, indexed anchors, and a
  hard maximum path depth.

- Database permissions remain the final security boundary; dedicated read-only
  accounts are recommended.

### Reproducible engine evidence

- Scores are normalized to the player at the root position.

- Centipawn and mate scores remain distinct.

- CPL is computed only when both comparable scores are centipawn scores.

- `compare_move` searches the best and played moves from the same root with the
  same requested budget.

- Principal variations are legally replayed in UCI and SAN.

- Responses preserve engine identity, options, search limits, depth, nodes, and
  elapsed engine time when available.

### Shared position identity

PostgreSQL and Neo4j use a four-field normalized FEN:

```text
piece placement · side to move · castling rights · en-passant target
```

Dropping move counters lets different move orders converge on the same position
key. Stockfish receives a valid six-field FEN generated from that shared key.

## Quick start

### Prerequisites

- Python 3.12+

- [`uv`](https://docs.astral.sh/uv/)

- Node.js 22+ and npm, for the React interface

- PostgreSQL with the project schema and loaded data

- Neo4j with the synchronized position graph

- A local [Stockfish](https://stockfishchess.org/download/) binary

- [Claude Code](https://code.claude.com) for the coaching plugin

### 1. Install the project

```bash
uv sync
```

This installs three executable MCP servers:

```text
.venv/bin/chessgraph-postgres-mcp
.venv/bin/chessgraph-neo4j-mcp
.venv/bin/chessgraph-stockfish-mcp
```

### 2. Configure local services

```bash
cp .env.template .env
```

Set the real values in `.env`:

```dotenv
POSTGRES_USER=chess_reader
POSTGRES_PASSWORD=change_me
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=chess
CHESS_USERNAME=your_chess_username

NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change_me
NEO4J_DATABASE=neo4j

STOCKFISH_PATH=/usr/games/stockfish

BACKEND_URL=http://127.0.0.1:8000
```

`CHESS_USERNAME` is the Chess.com account stored in the games. Keep the real
value in `.env`. Do not copy it into `CLAUDE.md`, the plugin, or any tracked file. Search
budgets and the other limits are documented in
[`.env.template`](.env.template).

Both stores must be reachable before the interface or the coaches are useful:
PostgreSQL on `5432` and Neo4j on `7687`. If Neo4j is down the coach says the
graph evidence is missing instead of guessing at it.

### 3. Load data if needed

If PostgreSQL and Neo4j are already populated, skip this step. Otherwise,
create the schemas from [`etl/sql_files/`](etl/sql_files/) and run:

```bash
uv run python etl/postgres_db/postgres_load.py
uv run python etl/postgres_db/load_stockfish_eval.py
uv run python etl/neo4j_db/neo4j_load.py
```

The loaders mutate or rebuild data; the MCP servers never invoke them.

### 4. Install the Claude Code plugin

The coach, its skills, and the three MCP servers ship as the `chessgraph`
plugin. This repository is also its marketplace:

```bash
claude plugin marketplace add /path/to/ChessGraph-MCP
claude plugin install chessgraph@chessgraph
```

On first use, Claude Code asks for `chessgraph_home`, the absolute path of this
checkout. You can also set it with `/plugin configure chessgraph@chessgraph`.
The servers start with `uv run --directory <chessgraph_home>`, so they read this
repository's `.env`. No credential is stored in the plugin.

What you get:

| Component | Use |
| --- | --- |
| `chess-coach` agent | Answers from the tools only, in positional terms |
| `/chessgraph:explain-position <FEN>` | Evaluation, best move, why, and whether you reached it |
| `/chessgraph:review-game [id]` | Largest mistakes, same-root comparison, one lesson |
| `/chessgraph:training-plan` | Strengths, target family, four tasks |
| `/chessgraph:opening-check [FEN]` | Your moves against theory, with scores |
| `/chessgraph:status` | Are PostgreSQL, Neo4j and Stockfish up? |

Claude Code names the tools `mcp__plugin_chessgraph_<server>__<tool>`. For
example:

```text
mcp__plugin_chessgraph_postgres__get_blunders
mcp__plugin_chessgraph_neo4j__get_position_moves
mcp__plugin_chessgraph_stockfish__compare_move
```

PostgreSQL and Neo4j may serve parallel reads. Stockfish calls stay serialized,
because one persistent UCI process serves that server. See
[`docs/plugin.md`](docs/plugin.md).

### 5. Verify

```bash
uv run pytest
```

Optional live-service tests:

```bash
CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py
```

Inspect a server with the official MCP development tooling:

```bash
uv run mcp dev chess_mcp/stockfish/server.py
```

### 6. Run the retrieval API

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Seventeen routes serve the interface, the coaching reads, and the coach:

| Route | Purpose |
| --- | --- |
| `GET /health` | Liveness check |
| `GET /api/player` | Player summary: games, results, average ratings, date range |
| `GET /api/recap` | Rating-band recap: win rate, lines, clocks, results |
| `GET /api/games` | Filter games by player, type, outcome, ECO, and date |
| `GET /api/games/{game_id}` | One game's metadata and movetext |
| `GET /api/games/{game_id}/moves` | Paged moves, clocks, and stored evaluations |
| `GET /api/lessons/openings` | Opening lessons for a colour |
| `GET /api/lessons/endgames` | Endgame lessons for the player's rating tier |
| `GET /api/coach/brief` | Strengths, weakest target, calculation, four tasks |
| `GET /api/coach/plan` | The ranked training plan |
| `GET /api/openings` | Opening theory for an exact normalized position |
| `GET /api/positions` | Neo4j position context and outgoing moves |
| `POST /api/engine/analyze` | Bounded MultiPV analysis |
| `POST /api/engine/compare` | One played move against the best move, same root |
| `POST /api/engine/validate` | Replay a UCI line into legal SAN and FENs |
| `POST /api/coach/chat` | The in-app coach, streamed as server-sent events |
| `GET /api/coach/status` | Whether the coach runs on Claude or offline |

The UI proxies `/api` to `BACKEND_URL`. See [`backend/README.md`](backend/README.md).
The Stockfish routes start their own engine on first use. The Stockfish MCP
server keeps a separate engine of its own.

### 7. Run the UI

```bash
cd ui
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The app has three modes:

- **Home** — the default view. A rating-band recap counted from PostgreSQL
  through `GET /api/recap`. Pick a band and the charts recompute; each card
  opens into the chart and table behind it. The favourite line in a band is the
  stored opening name with the most games, so a line that was played can still
  rank behind a larger one.
- **Training** — the ranked plan from `GET /api/coach/plan`, drilled on the
  board with a hint drawn from your own stored move, and the live coach beside it.
- **My games** — stored games grouped by time control, with the review jumping
  to a game's recorded key moment.

Every panel is a live read: the recap, games, lessons, coaching brief, plan, and
position analysis all come from the retrieval API. There is no sample data in
the interface.

### The in-app coach

The coach panel posts to `POST /api/coach/chat`, and the API streams the answer
back as server-sent events. The UI lights each evidence chip (Games, Graph,
Stockfish) as the matching tool runs.

The coach has two modes:

- **Claude.** Used when `ANTHROPIC_API_KEY` is set in `.env`.
  - The API runs a tool loop on the Messages API (`CLAUDE_MODEL`, default
    `claude-opus-5-5`, with effort `CLAUDE_EFFORT`, default `low`).
  - It uses twelve read-only tools that mirror the MCP contracts.
  - Usernames are replaced by "you" and "opponent" before any tool result
    leaves the machine.
  - `CLAUDE_REFUSAL_FALLBACK=default` lets the API retry a refused turn on a
    fallback model.
- **Offline evidence.** Used when there is no key, or when `COACH_MODE=offline`
  is set.
  - The same tools run in a fixed plan: a position question gets Stockfish plus
    the graph, a training question gets the coaching brief, and a game question
    gets the largest mistakes plus a same-root comparison.
  - The results are printed without a model and labelled as offline.

The key stays in the API process. See [`backend/README.md`](backend/README.md).

Other UI commands:

```bash
cd ui
npm test         # clock rules, statistics, plan ranking, and coach transport
npm run lint     # oxlint
npm run build    # type-check and production bundle
npm run preview  # serve the production bundle
```

See [`ui/README.md`](ui/README.md) for the interface structure and libraries.

## MCP surface

<details>
<summary><strong>PostgreSQL tools</strong></summary>

| Tool | Purpose |
| --- | --- |
| `list_games` | Filter games by player, type, outcome, ECO, and date |
| `get_game` | Retrieve one game's metadata and PGN movetext |
| `get_game_moves` | Page through ordered moves, FENs, clocks, and evaluations |
| `get_player_summary` | Aggregate results and ratings |
| `get_blunders` | Find the data owner's or a named player's evaluated mistakes |
| `get_coaching_brief` | Rank opening families by result and surface repeated mistakes |
| `find_position_occurrences` | Find games containing an exact normalized FEN |
| `lookup_opening` | Retrieve opening theory for a position |
| `lookup_endgame_positions` | Retrieve filtered endgame benchmarks |

Resource: `chessgraph://postgres/schema`

</details>

<details>
<summary><strong>Neo4j tools</strong></summary>

| Tool | Purpose |
| --- | --- |
| `get_position_context` | Retrieve a position with opening and endgame links |
| `get_position_moves` | Compare outgoing personal and theory moves |
| `find_transpositions` | Find bounded paths to convergent graph positions |
| `get_game_blunders` | Retrieve graph-linked mistakes for one game |
| `get_recurring_blunder_positions` | Rank repeated mistake positions |
| `get_endgame_context` | Retrieve endgame patterns and benchmark positions |

Resource: `chessgraph-neo4j://schema`

</details>

<details>
<summary><strong>Stockfish tools</strong></summary>

| Tool | Purpose |
| --- | --- |
| `analyze_position` | Run bounded depth, node, or time-based MultiPV analysis |
| `compare_move` | Compare a legal played move with the best move from one root |
| `validate_line` | Replay UCI moves and return legal SAN/FEN evidence |

Resource: `chessgraph-stockfish://capabilities`

</details>

See [`docs/mcp.md`](docs/mcp.md) and the package-specific READMEs under
[`chess_mcp/`](chess_mcp/) for contracts, semantics, and extension guidance.

## Project structure

```text
ChessGraph-MCP/
├── chess_mcp/                 modular MCP package
│   ├── postgres/              relational repositories, recap, training plan, server
│   ├── neo4j/                 graph repositories, models, server
│   └── stockfish/             UCI lifecycle, scoring, models, server
├── etl/
│   ├── postgres_db/           game, theory, and engine-evaluation loaders
│   ├── neo4j_db/              graph synchronization
│   └── sql_files/             PostgreSQL schema
├── backend/                   FastAPI reads for the UI
├── ui/                        React coach, all panels reading the API
│   └── src/
│       ├── views/             Home, Training, and My games
│       ├── data/              API-backed reads plus name and type helpers
│       ├── lib/               chess rules, clocks, evaluations, graph, stats
│       ├── components/        board, coach panel, eval bar, cards
│       └── services/          coach transport and engine calls
├── plugins/chessgraph/        Claude Code plugin: MCP servers, coach agent, skills
├── .claude-plugin/            local marketplace manifest
├── docs/                      operations and MCP reference
├── tests/                     unit and opt-in integration tests
├── CHESS.md                   chess-domain reference
└── STOCKFISH.md               engine and NNUE reference
```

## Data sources

- Personal PGN archives exported from [Chess.com](https://www.chess.com/)
- [Lichess chess openings](https://huggingface.co/datasets/Lichess/chess-openings)
- [Endgame Atlas Bench](https://huggingface.co/datasets/Agusanso/EndgameAtlasBench)

Dataset licenses and terms remain those of their respective publishers. Personal
game records may contain usernames and should be treated as private data.

## Current scope

ChessGraph MCP is a local evidence layer, not a complete coaching application.
It currently provides:

- local stdio MCP servers, packaged as a Claude Code plugin;
- a FastAPI retrieval process for the interface, using the same repositories;
- read-only runtime tools, with no arbitrary query surface;
- existing-data analysis over the loaded games;
- ranked coaching briefs and a training plan derived from those games;
- deterministic validation and typed evidence;
- a local React interface for Home, Training, and game review, reading the API
  rather than carrying sample data.

The coach persona and skills live in [`plugins/chessgraph/`](plugins/chessgraph/).
Project instructions for Claude Code live in [`CLAUDE.md`](CLAUDE.md).

Not yet built: persisting lessons or drilling history back into the stores,
running the retrieval API as a remote HTTP or OAuth service, and automatically
verifying every natural-language strategic claim the model produces. The
training plan ranks what to work on next; it does not yet record whether a drill
was completed.

## Documentation

- [Retrieval API](backend/README.md)

- [Coach interface](ui/README.md)

- [Claude Code plugin](docs/plugin.md)

- [MCP setup, security, and troubleshooting](docs/mcp.md)

- [MCP package concepts](chess_mcp/README.md)

- [PostgreSQL server](chess_mcp/postgres/README.md)

- [Neo4j server](chess_mcp/neo4j/README.md)

- [Stockfish server](chess_mcp/stockfish/README.md)

- [Chess concepts](CHESS.md)

- [Stockfish and NNUE concepts](STOCKFISH.md)

- [Official MCP documentation](https://modelcontextprotocol.io/docs)

## License

Released under the [MIT License](LICENSE).
