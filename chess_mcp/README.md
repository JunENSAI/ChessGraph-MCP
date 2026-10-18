# Chess MCP package

## What this package provides

`chess_mcp` contains three independent Model Context Protocol servers that give
an agent controlled access to:

- PostgreSQL game history and structured chess telemetry;

- Neo4j position relationships and recurring patterns;

- Stockfish engine analysis and legal-line validation.

The package does not contain the coaching model itself. Hermes-Agent or another
MCP host decides which tools to call and turns their structured evidence into a
coaching response.

```text
Hermes-Agent
├── PostgreSQL MCP ── personal games, metrics, openings, endgames
├── Neo4j MCP ─────── position graph, theory, transpositions, patterns
└── Stockfish MCP ─── evaluation, candidate lines, move comparison
```

Each server is a separate stdio process. This keeps dependencies and failures
isolated and lets the host combine evidence without coupling Stockfish to either
database.

## Why MCP is used

MCP gives the agent discoverable, typed interfaces instead of unrestricted
database or shell access. This package uses two MCP primitives:

- **Tools** are model-controlled operations such as `get_blunders`,
  `get_position_moves`, and `compare_move`.
- **Resources** are read-only explanatory documents that describe database
  schemas or Stockfish score semantics.

Every tool has typed inputs and structured outputs generated from Python type
hints and Pydantic models. Database tools are curated and read-only: there is no
free-form SQL or Cypher tool. Tool annotations also declare that operations are
read-only, non-destructive, and idempotent.

These constraints matter because an agent should receive only the information
needed for coaching, with predictable limits and no ability to modify the data
loaded by the ETL pipeline.

## Package structure

```text
chess_mcp/
├── config.py       validated environment configuration
├── chess.py        shared FEN and legal-move utilities
├── errors.py       safe MCP error conversion
├── models.py       shared response models
├── postgres/       relational game-history server
├── neo4j/          positional graph server
└── stockfish/      deterministic engine-analysis server
```

### Shared concepts

#### FEN identity

PostgreSQL and Neo4j identify positions with the first four FEN fields:

1. piece placement;

2. side to move;

3. castling rights;

4. en-passant target.

Halfmove and fullmove counters are removed so transpositions reach the same
database key. Stockfish requires a complete six-field FEN, so `chess.py`
supplies default counters when a normalized four-field key is provided.

Always use the shared helpers rather than implementing a second normalization
rule. Otherwise a position may be valid for Stockfish but fail to match the
same position in PostgreSQL or Neo4j.

#### Configuration

`config.py` loads `.env` without overriding already-exported variables and
creates immutable settings objects. It validates required credentials, numeric
limits, engine paths, and search bounds. Settings are cached for the lifetime
of each stdio process.

Important groups are:

- `POSTGRES_*` and `POSTGRES_STATEMENT_TIMEOUT_MS`;

- `NEO4J_*` and `NEO4J_MAX_PATH_DEPTH`;

- `STOCKFISH_*` search and resource limits;

- `MCP_MAX_RESULTS`, shared by database result sets.

#### Error handling

Invalid user arguments become actionable MCP tool errors. Unexpected internal
failures are logged to stderr and converted to safe messages so credentials and
connection strings are not returned to the model. Stdio protocol messages use
stdout, so application logging must never be written there.

## How the servers work together

A typical coaching workflow is:

1. Use PostgreSQL to select a game or its highest-centipawn-loss moves.

2. Read the move's `fen_before_norm` and played UCI move.

3. Use Neo4j to find personal continuations, theory moves, opening context, or
   recurring mistakes at that position.

4. Use Stockfish `compare_move` to analyze the best move and played move from
   the same root with the same search budget.

5. Use `validate_line` before making a concrete tactical claim.

6. Let the model explain only facts supported by the returned records, legal
   lines, and engine provenance.

The databases provide historical evidence; Stockfish provides live analytical
evidence. Neither source alone explains why a move is instructive. The agent
combines them into a lesson while keeping facts separate from hypotheses.

## Running the servers

Install the project:

```bash
uv sync
```

The configured entry points are:

```text
.venv/bin/chessgraph-postgres-mcp
.venv/bin/chessgraph-neo4j-mcp
.venv/bin/chessgraph-stockfish-mcp
```

They are intended to be launched by an MCP host, not used as interactive
terminal programs. See the repository-level `docs/mcp.md` and
`agent/hermes-mcp.example.yaml` for setup and Hermes-Agent configuration.

## Extending the package

When adding a capability:

1. put database or engine behavior in the service/repository layer;

2. represent the result with a typed model;

3. expose a small MCP tool in `server.py`;

4. validate and bound every caller-controlled limit;

5. keep database statements parameterized and read-only;

6. add mocked unit tests before an opt-in live integration test;

7. update the relevant folder README and MCP resource semantics.

Do not make the MCP layer perform ETL writes or ask an LLM to invent chess
facts that deterministic code can validate.
