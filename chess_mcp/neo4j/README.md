# Neo4j MCP server

## What this folder provides

This package exposes the positional knowledge graph (schema v2) through eight
curated, read-only MCP tools:

- `get_position_context` returns one position with its phase, material,
  average stored eval, exact opening, opening families whose lines pass
  through it, endgame type and stored engine best move;

- `get_position_moves` returns theory moves and played moves, split by mover
  (`by`: `owner` or `opponent`), each scored from the mover's side;

- `find_transpositions` finds bounded paths from a position to positions that
  at least two distinct predecessors reach;

- `get_game_blunders` returns the owner's mistakes in one game at or above a
  severity (`inaccuracy`, `mistake`, `blunder`);

- `get_recurring_blunder_positions` ranks positions where the owner went wrong
  in several games;

- `get_endgame_context` returns endgame classifications and Endgame Atlas
  benchmark positions;

- `get_games_through_position` lists the owner's games that reached a
  position, with the owner's score from it;

- `get_theory_exits` ranks where games leave opening theory and with which
  move.

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

The full schema, with properties, is the `chessgraph-neo4j://schema` resource
and [`etl/neo4j_db/neo4j_init.md`](../../etl/neo4j_db/neo4j_init.md).

### Nodes

- `Position` is identified by the four-field `fen_norm`.
- `Game` mirrors PostgreSQL game metadata using `game_id`.
- `Player` is one Chess.com account; `is_owner` marks the data owner. The tools
  never return usernames.
- `Opening` is identified by `epd_norm`; `OpeningFamily` groups openings.
- `EndgamePattern` is one Endgame Atlas material type.
- `ChessGraphMeta` records the schema version and load counts.

### Relationships

- `PLAYED_MOVE {uci_move, by}`: a move from the stored games, one edge per
  mover, with the mover's results, centipawn loss and severity counts.
- `THEORY_MOVE {uci_move}`: a book move, with every ECO code that plays it.
- `ENGINE_BEST`: the most frequent stored Stockfish best move.
- `CLASSIFIED_AS`, `IN_OPENING`, `IN_FAMILY`: opening classification.
- `HAS_ENDGAME_TYPE`: Atlas benchmarks and game positions of six pieces or fewer.
- `PLAYED_AS`, `REACHED`, `OPENED_WITH`, `LEFT_THEORY_AT`, `ENTERED_ENDGAME`:
  a game's players, path and milestones.
- `MISTAKE_IN`: an owner move with a centipawn loss of 50 or more.

`PLAYED_MOVE` and `THEORY_MOVE` may both exist for the same UCI move. Their
statistics mean different things and should not be merged by the agent.

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

- played edges carry the number of distinct games, wins/draws/losses and
  `score_pct` from the **mover's** side, average centipawn loss, average eval
  after the move, and inaccuracy/mistake/blunder counts. Filter with
  `by="owner"` for the player's own choices;
- theory edges carry `eco_codes` and no results.

Use sample size alongside score. A high percentage from one game is weak
evidence.

### Transpositions

`find_transpositions` explores outgoing paths from the supplied position up to
four plies and keeps targets reached from at least two distinct positions. One
path is kept per move sequence, since a played move has an owner edge and an
opponent edge. It does not perform an exhaustive chess search.

### Mistakes, games and endgames

`MISTAKE_IN` edges are historical ETL results from stored depth-limited
Stockfish evaluations, not live analysis. Use Stockfish to reanalyze a critical
position. Stored mate scores are flattened to +/-10000, so `mate_swing` marks
a loss of 5,000 cp or more.

`material_sig` and `EndgamePattern.endgame_type` share the Endgame Atlas
notation (White first, `KRPvKR`), so a game position links to a hub when the
Atlas covers that material.

## Data caveats

- `visit_games` counts distinct games that reached the position.
- `eval_cp` on a position is an average of stored evals from the side to move;
  `eval_samples` says how many.
- PostgreSQL has no clock data for these games, so the graph has none.
- Opening classification may return several openings for positions shared by
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
