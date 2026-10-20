<div align="center">

# ChessGraph MCP

### A local evidence layer for personalized chess coaching

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

- **Hermes-Agent explains** the combined evidence as a personalized lesson.

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
        api["FastAPI retrieval"]
        pgMcp["PostgreSQL MCP: 8 tools"]
        graphMcp["Neo4j MCP: 6 tools"]
        sfMcp["Stockfish MCP: 3 tools"]
        stockfish["Stockfish UCI"]
    end

    ui["React coach"]
    host["Hermes-Agent and frontier model"]
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
    ui -->|"questions"| host
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
bounded for Hermes. The API serves the facts the interface can draw before a
question is asked: the rating-band recap, training lessons, and the game
library. Hermes explains; it does not assemble the page.

## What the agent can ask

| Evidence source | Best suited for | MCP capabilities |
| --- | --- | --- |
| PostgreSQL | Game selection, longitudinal statistics, move records, openings, endgames | 8 curated tools, paginated move retrieval, statement timeouts |
| Neo4j | Theory versus personal choices, transpositions, recurring positions, graph context | 6 curated tools, anchored queries, maximum traversal depth |
| Stockfish | Fresh position analysis, candidate comparison, WDL, legal variations | MultiPV, same-root move comparison, line validation |

Examples:

- “Show my largest rapid-game mistakes and explain the top three.”

- “Where did I leave opening theory, and what did I usually play instead?”

- “Do different move orders in my games transpose into this position?”

- “Compare my move with Stockfish's best move using the same search budget.”

- “Which endgame patterns recur in my losses?”

## Evidence flow for a coaching answer

```mermaid
sequenceDiagram
    actor User
    participant Hermes as Hermes-Agent
    participant PG as PostgreSQL MCP
    participant Graph as Neo4j MCP
    participant SF as Stockfish MCP

    User->>Hermes: Why was this move a mistake?
    Hermes->>PG: get_game_moves and get_blunders
    PG-->>Hermes: FEN, played move, CPL, clock, game context
    Hermes->>Graph: get_position_context and get_position_moves
    Graph-->>Hermes: Theory, personal choices, recurring patterns
    Hermes->>SF: compare_move from the same root
    SF-->>Hermes: Best line, played line, score, WDL, provenance
    Hermes->>SF: validate_line for any cited continuation
    SF-->>Hermes: Legal UCI, SAN, and resulting FENs
    Hermes-->>User: Verified explanation and actionable lesson
```

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

- An MCP host such as [Hermes-Agent](https://github.com/NousResearch/hermes-agent)

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

HERMES_API_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=
BACKEND_URL=http://127.0.0.1:8000
```

`CHESS_USERNAME` is the Chess.com account stored in the games. Keep the real
value in `.env`. Do not copy it into `AGENTS.md` or the Hermes seeds. Search
budgets and the other limits are documented in
[`.env.template`](.env.template).

### 3. Load data if needed

If PostgreSQL and Neo4j are already populated, skip this step. Otherwise,
create the schemas from [`etl/sql_files/`](etl/sql_files/) and run:

```bash
uv run python etl/postgres_db/postgres_load.py
uv run python etl/postgres_db/load_stockfish_eval.py
uv run python etl/neo4j_db/neo4j_load.py
```

The loaders mutate or rebuild data; the MCP servers never invoke them.

### 4. Connect Hermes-Agent

Merge [`agent/hermes-mcp.example.yaml`](agent/hermes-mcp.example.yaml) into
`~/.hermes/config.yaml`, then adjust its absolute executable paths.

Hermes registers tools with a server prefix. For example:

```text
mcp_chess_postgres_get_blunders
mcp_chess_neo4j_get_position_moves
mcp_chess_stockfish_compare_move
```

PostgreSQL and Neo4j may serve parallel reads. Stockfish parallel calls remain
disabled because one persistent UCI process is deliberately serialized.

Copy the identity seeds before the first coaching session. Hermes loads
`SOUL.md` only from `$HERMES_HOME`, and memory only from
`$HERMES_HOME/memories/`. See [`agent/README.md`](agent/README.md).

The coach panel calls Hermes through a Vite proxy. Set `HERMES_API_URL` and
`HERMES_API_KEY` from [`.env.template`](.env.template). `HERMES_API_KEY` must
match `API_SERVER_KEY` in `~/.hermes/.env`. The Vite dev and preview servers
add the bearer header, so the key stays on the server side. Do not expose it
as a `VITE_` variable.

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

The UI proxies `/api` to `BACKEND_URL`. Routes cover the rating-band recap,
game and move reads, opening-file lookup, Neo4j position context, and a
bounded Stockfish search. See [`backend/README.md`](backend/README.md). The
Stockfish route starts its own engine on first use. Hermes continues to use
the separate engine inside the Stockfish MCP server.

### 7. Run the UI

```bash
cd ui
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The app has three modes:
Training, My games, and Recap. Each one reads PostgreSQL through the retrieval
API:

- Recap uses `GET /api/recap`. The favorite line in a rating band is the stored
  opening name with the most games, so a line that was played can still rank
  behind a larger one.
- Training uses `GET /api/lessons/openings` and `GET /api/lessons/endgames`.
  Openings and defenses are the account's most-played lines, each with one
  stored theory line. Endgames are technique positions from the elo tier
  nearest the account's average rating.
- My games uses `GET /api/player`, `GET /api/games`, and
  `GET /api/games/{id}/moves`. The review opens on the move with the largest
  stored centipawn loss.

If the API or PostgreSQL is unavailable, the mode shows that error and a
retry. An empty database says that nothing is stored. Sample lines in
[`ui/src/data/demo.ts`](ui/src/data/demo.ts) are synthetic fixtures for unit
tests and are not shown in the interface.

Other UI commands:

```bash
cd ui
npm test         # clock rules, lesson lines, and the game-library mapping
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
│   ├── postgres/              relational repositories, models, server
│   ├── neo4j/                 graph repositories, models, server
│   └── stockfish/             UCI lifecycle, scoring, models, server
├── etl/
│   ├── postgres_db/           game, theory, and engine-evaluation loaders
│   ├── neo4j_db/              graph synchronization
│   └── sql_files/             PostgreSQL schema
├── backend/                   FastAPI reads for the UI
├── ui/                        React coach; lessons, games, and recap from the API
├── agent/                     Hermes persona, memory seeds, MCP config example
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

- local stdio MCP transport for Hermes;
- a FastAPI retrieval process for the interface, using the same repositories;
- read-only runtime tools;
- existing-data analysis;
- deterministic validation and typed evidence;
- a local React interface for training, game review, and rating-band recap.

Committed Hermes seeds live in [`agent/`](agent/) (`SOUL.md`, `MEMORY.md`,
`USER.md`). Project instructions live in [`AGENTS.md`](AGENTS.md). The coach
panel calls Hermes through the Vite proxy and answers from the MCP evidence.
The recap, training lessons, and game library are read from PostgreSQL.
Remote HTTP/OAuth deployment, lesson persistence, and automatic verification
of every natural-language strategic claim are outside the current scope.

## Documentation

- [Retrieval API](backend/README.md)

- [Coach interface](ui/README.md)

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