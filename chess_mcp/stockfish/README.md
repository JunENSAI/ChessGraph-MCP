# Stockfish MCP server

## What this folder provides

This package exposes deterministic chess analysis through three read-only MCP
tools:

- `analyze_position` returns bounded MultiPV candidate lines;

- `compare_move` compares Stockfish's best move with one legal played move from
  the same root position and search budget;

- `validate_line` legally replays UCI moves and returns SAN plus resulting FENs.

The `chessgraph-stockfish://capabilities` MCP resource explains the score and
search semantics an agent must follow.

## Why Stockfish is used

Stockfish is the calculation authority in the coaching system. It searches
legal continuations and provides candidate moves, scores, WDL estimates, and
principal variations. This is stronger evidence than asking a language model
to guess the consequence of a move.

Stockfish does not produce a complete human explanation. A principal variation
shows one engine-preferred continuation, and a numerical score does not identify
the tactical or strategic mechanism by itself. The coaching model should use
these results with database context and verified board facts.

## Core analysis concepts

### Root-player point of view

Raw engine scores can be represented from different perspectives. This package
normalizes every returned score to the player whose turn it is in the supplied
root FEN.

That rule is essential when comparing White and Black moves. A positive score
always favors the root player in this API; the agent should not apply an
additional sign inversion.

### Centipawn scores

A `cp` score is Stockfish's evaluation scale. Conventionally, 100 centipawns
are approximately one pawn unit, but a centipawn value is not a universal win
probability and depends on position, engine version, options, and search budget.

### Mate scores

A `mate` score retains its signed mate distance. It is never converted into a
large artificial centipawn number. Centipawn loss is therefore `null` whenever
either compared score is a mate score.

### Centipawn loss

For two centipawn scores normalized to the root player:

```text
CPL = max(0, best_score - played_score)
```

`compare_move` obtains both values from the same pre-move board and with the
same requested search limit. This is more meaningful than subtracting
evaluations from unrelated before/after searches.

### MultiPV

MultiPV asks Stockfish for several ranked candidate lines. Use it when the
coaching question requires alternatives, trade-offs, or ambiguity. Higher
MultiPV values divide search effort across more candidates and are more
expensive than a single principal variation.

### WDL

When the installed engine supports `UCI_ShowWDL`, each line can include wins,
draws, and losses in permille from the root player's point of view. WDL provides
practical context but remains an engine estimate under its calibration
conditions, not the player's guaranteed result.

### Principal variation

A principal variation is the engine's representative best-play line at the
completed search. This package legally replays the line and returns both UCI
and SAN. It is evidence for a claim, not proof that every alternative was
exhausted.

## How it is implemented

```text
MCP tool in server.py
        │
        ▼
StockfishService in engine.py
        │
        ├── input and search-limit validation
        ├── persistent UCI engine management
        └── legal PV replay and response construction
                │
                ▼
score normalization in scoring.py
                │
                ▼
typed models from models.py
```

### `engine.py`

`StockfishEngine` lazily launches one `python-chess` `SimpleEngine` process.
The process is reused because starting Stockfish for every tool call would add
latency and discard useful engine initialization.

A lock serializes all calls. UCI engines and their mutable search state must not
receive overlapping analyses from parallel MCP tool calls. The MCP lifespan
quits the child process during shutdown.

The configured `Threads`, `Hash`, and `UCI_ShowWDL` options are applied when the
engine starts and are included in returned provenance where relevant.

`StockfishService` validates FENs and legal moves, clamps caller budgets, builds
`python-chess` search limits, and maps engine output to typed responses.

### `scoring.py`

This module owns point-of-view normalization, WDL normalization, legal PV
replay, engine-info conversion, and CPL calculation. Keeping these operations
outside the MCP adapter makes them deterministic and independently testable.

### `models.py`

The models distinguish:

- search limit type and actual bounded value;

- `cp` versus `mate` scores;

- WDL values;

- UCI and SAN principal variations;

- engine identity, options, depth, selective depth, nodes, and time.

The provenance fields allow a result to be interpreted and reproduced instead
of presenting an engine score as context-free truth.

### `server.py`

The server exposes the three service methods as structured MCP tools, converts
input failures to actionable tool errors, publishes the capabilities resource,
logs only to stderr, and closes the engine during shutdown.

## Choosing a search budget

`limit_type` supports:

- `depth`: nominal search depth in plies;

- `nodes`: maximum searched node count;

- `time`: engine time in milliseconds.

If no depth value is supplied, `STOCKFISH_DEFAULT_DEPTH` is used. Requested
values are clamped to configured maxima, and the response reports the actual
limit used.

Depth is convenient for repeatable local comparisons, nodes are useful for a
machine-independent work budget, and time is useful for interactive latency.
Results from different budget types should not be treated as perfectly
equivalent.

## Recommended coaching workflow

1. Obtain the exact pre-move FEN and played UCI move from PostgreSQL.

2. Call `compare_move` at a moderate depth.

3. Inspect both legal principal variations and WDL, not only CPL.

4. If the result is tactical, ambiguous, or close, rerun with a larger budget
   and optionally use `analyze_position` with MultiPV.

5. Call `validate_line` for any line cited independently by the agent.

6. State which facts come from the engine and which coaching interpretation is
   a hypothesis.

Do not infer “fork,” “pin,” “king weakness,” or another motif from CPL alone.
The board and returned variations must support that claim.

## Configuration

```text
STOCKFISH_PATH=/usr/games/stockfish
STOCKFISH_DEFAULT_DEPTH=10
STOCKFISH_MAX_DEPTH=15
STOCKFISH_MAX_NODES=5000000
STOCKFISH_MAX_TIME_MS=30000
STOCKFISH_MAX_MULTIPV=5
STOCKFISH_THREADS=1
STOCKFISH_HASH_MB=128
```

`STOCKFISH_DEPTH` remains a legacy fallback used when the MCP-specific default
is absent. Keep Hermes tool timeouts above the maximum allowed engine time.

## Extending safely

Keep protocol code thin and place deterministic behavior in the service or
scoring modules. Preserve explicit score perspective and mate handling, replay
every returned line legally, include search provenance, and add tests that use
a fake engine rather than requiring a binary for the normal unit suite.
