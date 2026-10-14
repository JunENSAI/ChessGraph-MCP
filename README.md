# ChessGraph-MCP

Building a chess Agentic setup that bridges the gap between deterministic game-tree calculation and semantic coaching. Permit the agent to access on stockfish and additional graph knowledge to help it understand what moves are playable on differents positions.

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
│  • ELO & results      │       │ • [:PLAYED] edges     │
│  • ACPL / Blunder %   │       │ • [:THEORY] links     │
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