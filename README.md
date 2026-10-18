# ChessGraph-MCP

ChessGraph-MCP combines deterministic engine analysis with personal game data
and graph knowledge to support an evidence-based chess coach.

## System Architecture

```text
  [Chess.com PGN Archives]        [Hugging Face Datasets (Parquet/CSV)]
     (1500+ ELO Games)              (ECO Openings & Endgame Theory)
             │                                     │
             └──────────────┬──────────────────────┘
                            ▼
                ┌───────────────────────┐
                │   ETL & Normalizer    │  (Python / Polars / python-chess)
                └───────────┬───────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
┌───────────────────────┐       ┌───────────────────────┐
│      PostgreSQL       │       │         Neo4j         │
│  Game Telemetry & SQL │       │ Positional GraphRAG   │
│  • Game Type          │       │ • (:Position {fen})   │
│  • ELO & results      │       │ • [:PLAYED_MOVE]      │
│  • ACPL / Blunder %   │       │ • [:THEORY_MOVE]      │
└───────────┬───────────┘       └───────────┬───────────┘
            │                               │
            └───────────────┬───────────────┘
                            ▼
                ┌───────────────────────┐       ┌───────────────────────┐
                │     Hermes-Agent      │◄─────►│  Stockfish MCP Server │
                │  Orchestration Layer  │  MCP  │  • MultiPV Eval       │
                │  (Cypher + SQL + MCP) │       │  • WDL Probabilities  │
                └───────────────────────┘       │  • Positional Motifs  │
                                                └───────────────────────┘
```

## Local MCP servers

The repository provides three modular, read-only MCP servers:

- PostgreSQL for games, move telemetry, player summaries, openings, endgames,
  and evaluated mistakes.
- Neo4j for position context, personal/theory continuations, transpositions,
  recurring blunders, and endgame relationships.
- Stockfish for bounded MultiPV analysis, same-root move comparison, WDL,
  principal variations, and legal-line validation.

They use the official Python MCP SDK v2 and run over stdio for a local host such
as Hermes-Agent.

```bash
cp .env.template .env
# Fill in local database credentials and STOCKFISH_PATH.
uv sync
uv run pytest
```

Installed entry points:

```text
.venv/bin/chessgraph-postgres-mcp
.venv/bin/chessgraph-neo4j-mcp
.venv/bin/chessgraph-stockfish-mcp
```

See [the MCP guide](docs/mcp.md) for the complete tool catalog, read-only role
recommendations, MCP Inspector usage, and troubleshooting. A Hermes-Agent
configuration template is available at
[`agent/hermes-mcp.example.yaml`](agent/hermes-mcp.example.yaml).

## Safety and evidence

Database servers expose curated, parameterized reads only. All result sets and
graph traversal depths are bounded. Stockfish scores retain an explicit point
of view; mate scores are not converted to fake centipawns; and cited principal
variations are replayed legally before being returned.

The MCP layer does not reload ETL data or write analysis back to either
database. Existing loaders remain under [`etl/`](etl/).