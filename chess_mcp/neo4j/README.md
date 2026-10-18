# Neo4j MCP server

## What this folder provides

This package exposes the positional knowledge graph through six curated,
read-only MCP tools:

- `get_position_context` returns one position with opening and endgame links;

- `get_position_moves` returns outgoing personal and theory moves;

- `find_transpositions` finds bounded paths from a position to graph nodes with
  more than one incoming move path;

- `get_game_blunders` returns graph-linked mistakes for one game;

- `get_recurring_blunder_positions` ranks repeated mistake positions;

- `get_endgame_context` returns endgame classifications and benchmark
  positions.

The `chessgraph-neo4j://schema` MCP resource describes node labels,
relationships, properties, and ETL caveats.

## Why Neo4j is used

Chess positions form a directed state-transition graph. Different move orders
can reach the same normalized FEN, so they naturally converge on one
`Position` node. This makes Neo4j useful for:

- finding transpositions;

- comparing personal moves with theory from the same position;

- following short move paths;

- connecting positions to openings, endgames, and games;

- recognizing repeated mistake locations across game history.

PostgreSQL remains the better source for ordered game records and broad
aggregations. Stockfish remains the authority for fresh position analysis.
Neo4j describes relationships already loaded by the ETL; a graph edge is not
new chess truth merely because it exists.

## Graph model

### Nodes

- `Position` is identified by the four-field `fen_norm`.

- `Opening` is identified by `epd_norm` and stores ECO/theory information.

- `EndgamePattern` groups endgame examples.

- `Game` mirrors selected PostgreSQL game metadata using `game_id`.

### Relationships

- `PLAYED_MOVE`: a personal-game transition between positions, with aggregate
  outcomes, centipawn loss, clocks, and move metadata.

- `THEORY_MOVE`: a reference opening transition.

- `CLASSIFIED_AS`: links a position to an opening.

- `HAS_ENDGAME_TYPE`: links a position to an endgame pattern.

- `BLUNDERED_IN`: links a mistake position to a game and ply.

Both `PLAYED_MOVE` and `THEORY_MOVE` may exist for the same UCI move. Their
statistics have different meanings and should not be merged by the agent.

## How it is implemented

```text
MCP tool in server.py
        │
        ▼
fixed Cypher method in repository.py
        │
        ▼
Neo4j execute_read transaction
        │
        ▼
typed graph model from models.py
```

### `server.py`

The server registers tools and the graph-schema resource. It converts expected
lookup/validation failures into actionable MCP tool errors and closes the Neo4j
driver during server shutdown.

Tools are annotated read-only, non-destructive, and idempotent.

### `repository.py`

The repository owns all Cypher. Queries are parameterized and run through
`session.execute_read` with Neo4j read access. Each query is anchored by
`fen_norm` or `game_id` and has a result limit.

Variable-length Cypher bounds cannot be supplied as query parameters. For that
reason, transposition depth is validated as an integer, clamped to the
configured maximum, checked against the hard whitelist `1..4`, and only then
inserted into the query text. All other values remain bound parameters.

### `models.py`

Pydantic models turn Neo4j maps into stable structured MCP output. Graph models
ignore unknown properties so adding non-breaking properties during a future ETL
run does not immediately break the server.

## Understanding the tools

### Position context

Use `get_position_context` first when you need classifications for an exact
position. A missing position is different from a position that exists without
an opening or endgame link.

### Personal moves versus theory

`get_position_moves` returns both relationship types:

- personal edges can include sample size, win rate, average centipawn loss, and
  clock information;
- theory edges can include ECO classification but do not represent the
  player's historical results.

Use sample size alongside win rate. A high percentage from one game is weak
evidence.

### Transpositions

`find_transpositions` explores outgoing paths from the supplied position up to
four plies and keeps targets with multiple incoming move edges. It answers
whether different move routes in the loaded graph converge on the same state.
It does not perform an exhaustive chess search.

### Blunders and endgames

Blunder relationships are historical ETL results, not live engine evaluations.
Use Stockfish to reanalyze a critical position when current evidence is needed.

Endgame classification has two sources: dataset `endgame_type` values and
computed position `material_sig` values. Their naming or orientation can differ.
Prefer an explicit `HAS_ENDGAME_TYPE` relationship over string equality.

## Data caveats

- `visit_count` is ETL-derived and may not be idempotent across repeated loads;
  treat it as approximate popularity.

- `BLUNDERED_IN` identity includes position, game, and ply. A repeated sync
  updates that event.

- Opening classification may return multiple results for positions shared by
  different theory lines.
  
- Graph statistics summarize loaded data; they do not imply causation or prove
  a strategic explanation.

## Configuration

Required variables:

```text
NEO4J_USER
NEO4J_PASSWORD
```

Optional variables:

```text
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_DATABASE=neo4j
NEO4J_MAX_PATH_DEPTH=4
MCP_MAX_RESULTS=100
```

Use a read-only Neo4j role where the installed edition supports granular
authorization. Keep a Community database local and use project-specific
credentials.

## Extending safely

Add a typed model, a fixed repository method, and then a thin MCP tool. Anchor
new traversals on an indexed identity, cap path depth and result count, and
avoid Cartesian products. Never interpolate caller text into Cypher; only a
validated integer path bound may be inserted where Cypher syntax forbids a
parameter.
