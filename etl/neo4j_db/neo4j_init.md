# NEO4J - Knowledge Graph 

Assume that **Neo4j** is installed and running locally [or you can download it on their official website]. There is `Community` and `Entreprise` edition. Because we are in demo, we can use the community edition.

 Neo4j is the world's leading native graph database and graph intelligence platform. It **stores and processes data as a network of connected nodes and relationships** rather than traditional tabular rows and columns.

---

## Graph

### Property Graph

A **Property Graph** (or Knowledge Graph) is a data structure that models information as a topological network of entities and the explicit connections between them. 

Unlike a relational database (PostgreSQL) that relies on rigid tables and computationally expensive `JOIN` operations across foreign keys.

A native graph database stores relationships as **index-free adjacency pointers** directly on disk—meaning traversing 10 moves ahead takes microseconds regardless of how many millions of games exist in the database.

### Graph Components in Neo4j

Every element in our Neo4j chess graph is built from four fundamental building blocks:

* **Nodes (Vertices):** The entities or states in the domain (drawn as circles). In our architecture, a node represents a board snapshot (`Position`), an opening classification (`Opening`), an endgame category (`EndgamePattern`), or a historical match (`Game`), a Chess.com account (`Player`), or an opening family (`OpeningFamily`).

* **Labels:** Tags that group nodes by their role (e.g., `:Position`, `:Opening`, `:EndgamePattern`, `:Game`, `:Player`).

* **Relationships (Edges):** Directed, named arrows connecting two nodes (e.g., `(:Position)-[:PLAYED_MOVE]->(:Position)`). Relationships always have a start node, an end node, and a direction.

* **Properties (Key-Value Attributes):** Metadata stored inside both **Nodes** *and* **Relationships**. To eliminate any notation ambiguity (for instance, knowing immediately that `e4` or `e2e4` moved a `"Pawn"` while `Nf3` moved a `"Knight"`), we store `moved_piece`, `from_square`, `to_square`, `promotion`, `is_capture` and `is_check` directly on the move relationship.

### Why Use a Graph Database Here Instead of Only PostgreSQL ?

Chess is inherently a **directed state-transition graph**, not a flat list of text moves:

1. **Automatic Transposition Resolution:** In sequential PGN text or SQL tables, `1. d4 Nf6 2. c4 e6` and `1. c4 e6 2. d4 Nf6` look like two completely different move sequences. In Neo4j, both paths naturally converge into the **exact same `(:Position)` node** (`fen_norm`), uniting all your games and opening theory that pass through that board state.

2. **Multi-Hop Exploration:** Cypher pattern matching (`-[:PLAYED_MOVE*1..4]->`) walks candidate branches natively, without recursive SQL self-joins. The MCP tools cap traversals at `NEO4J_MAX_PATH_DEPTH` (at most 4 plies) to keep every read bounded.

3. **Bridging Personal Habits to Theory:** Graph edges connect your personal `(:Position)` nodes directly to Hugging Face `(:Opening)` and `(:EndgamePattern)` hubs, allowing the coach to spot the exact node where your move diverges from book theory.

---

## Connection Setup

You can stard neo4j with :

```bash
neo4j start
```

Open **Neo4j Browser** at `http://localhost:7474` and connect using your credentials:

```plaintext
Connect URL : bolt://127.0.0.1:7687
Username    : neo4j
Password    : your_neo4j_password
```

Add the following variables to your root `.env` file:

```ini
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

---

## Load the graph

The loader reads PostgreSQL, builds every row in Python (`transform.py`, unit
tested), then writes in batches (`write.py`). It creates the constraints and
indexes itself.

```bash
uv run python etl/neo4j_db/neo4j_load.py --dry-run   # read and transform only; print row counts
uv run python etl/neo4j_db/neo4j_load.py --reset     # delete the chess labels, then load
```

The Neo4j database is shared with other projects. `--reset` runs
`MATCH (n:<Label>) CALL (n) { DETACH DELETE n } IN TRANSACTIONS` for the chess
labels only: `Position`, `Game`, `Opening`, `OpeningFamily`, `EndgamePattern`,
`Player`, `ChessGraphMeta`. The loader counts every label before and after and
exits with status 2 if a non-chess label changed. Without `--reset`, every
write is a `MERGE`, so a rerun updates rows in place but leaves edges that the
new data no longer produces.

`CHESS_USERNAME` must be set in `.env`: it decides which moves are the
owner's. Usernames are stored on `Player` nodes in the local database only; the
MCP tools never return them.

---

## Schema v2

```text
(:Player)-[:PLAYED_AS]->(:Game)-[:REACHED {ply}]->(:Position)
(:Game)-[:OPENED_WITH]->(:Opening)-[:IN_FAMILY]->(:OpeningFamily)
(:Game)-[:LEFT_THEORY_AT | ENTERED_ENDGAME]->(:Position)
(:Position)-[:PLAYED_MOVE {by} | THEORY_MOVE | ENGINE_BEST]->(:Position)
(:Position)-[:CLASSIFIED_AS | IN_OPENING]->(:Opening)
(:Position)-[:HAS_ENDGAME_TYPE]->(:EndgamePattern)
(:Position)-[:MISTAKE_IN]->(:Game)
(:ChessGraphMeta {schema_version: 2})
```

### Constraints and indexes

| Kind | Target |
| :--- | :--- |
| unique | `Position.fen_norm`, `Opening.epd_norm`, `EndgamePattern.endgame_type`, `Game.game_id`, `Player.username`, `OpeningFamily.name` |
| index | `Position.piece_count`, `Position.material_sig`, `Position.phase`, `Opening.eco_code`, `Game.game_type`, `Game.played_date` |
| relationship index | `PLAYED_MOVE.by` |

### Nodes

| Label | Properties |
| :--- | :--- |
| **`(:Position)`** | `fen_norm`, `turn_color`, `piece_count` (kings included), `material_sig`, `phase`, `is_theory`, `visit_games`, `eval_cp`, `eval_samples`, `best_move_uci`, `best_move_san` |
| **`(:Game)`** | `game_id`, `game_type`, `played_date` (date), `user_color`, `user_elo`, `opponent_elo`, `rating_band`, `user_outcome`, `result`, `termination`, `time_control`, `base_time_sec`, `increment_sec`, `eco_code`, `opening_name`, `total_plies` |
| **`(:Player)`** | `username`, `is_owner` |
| **`(:Opening)`** | `epd_norm`, `opening_id`, `eco_volume`, `eco_code`, `opening_name`, `family`, `pgn_line`, `uci_line` |
| **`(:OpeningFamily)`** | `name` |
| **`(:EndgamePattern)`** | `endgame_type` (*KRvK*, *KRPvKR*, …), `piece_count`, `benchmark_positions`, `avg_player_elo`, `sample_fen`, `sample_human_move` |
| **`(:ChessGraphMeta)`** | `name: 'chessgraph'`, `schema_version`, `loaded_at`, `count_<step>` for every write step |

### Relationships

| Relationship | Direction | Properties |
| :--- | :--- | :--- |
| **`[:PLAYED_MOVE]`** | `(:Position) -> (:Position)` | key `uci_move` + `by` (`owner`/`opponent`); `san_move`, `moved_piece`, `from_square`, `to_square`, `promotion`, `is_capture`, `is_check`, `games`, `times`, `wins`, `draws`, `losses`, `score_pct` (mover's side), `avg_cp_loss`, `avg_eval_after` (mover's side), `inaccuracies`, `mistakes`, `blunders`, `is_engine_best` |
| **`[:THEORY_MOVE]`** | `(:Position) -> (:Position)` | key `uci_move`; `san_move`, move metadata, `eco_codes` (every ECO line that plays it) |
| **`[:ENGINE_BEST]`** | `(:Position) -> (:Position)` | `uci`, `san`: most frequent stored Stockfish best move, when its target is in the graph |
| **`[:CLASSIFIED_AS]`** | `(:Position) -> (:Opening)` | the position is the opening's EPD |
| **`[:IN_OPENING]`** | `(:Position) -> (:Opening)` | `ply`: the position lies on that opening's line |
| **`[:IN_FAMILY]`** | `(:Opening) -> (:OpeningFamily)` | |
| **`[:HAS_ENDGAME_TYPE]`** | `(:Position) -> (:EndgamePattern)` | `benchmark: true` + `benchmark_move_uci`, `elo_tier`, `player_elo` for Atlas samples; `from_games: true` for game positions of six pieces or fewer |
| **`[:PLAYED_AS]`** | `(:Player) -> (:Game)` | `color`, `elo` |
| **`[:REACHED]`** | `(:Game) -> (:Position)` | `ply` (0 = start), `owner_to_move` |
| **`[:OPENED_WITH]`** | `(:Game) -> (:Opening)` | `ply` of the deepest named opening reached |
| **`[:LEFT_THEORY_AT]`** | `(:Game) -> (:Position)` | `ply`, `played_uci`, `played_san`, `by`: first move that is not a book move from that position |
| **`[:ENTERED_ENDGAME]`** | `(:Game) -> (:Position)` | `ply`, `material_sig` of the first endgame-phase position |
| **`[:MISTAKE_IN]`** | `(:Position) -> (:Game)` | owner moves only: `ply`, `severity`, `cp_loss`, `mate_swing`, `played_uci`, `played_san`, `best_uci` |

`ENTERED_ENDGAME` points at the position, not at an `EndgamePattern`: the
Endgame Atlas only covers some material, while every game has a first endgame
position. Follow `HAS_ENDGAME_TYPE` from that position when a hub exists.

### Rules

- **Perspective.** `Position.eval_cp` is from the side to move: the average
  `eval_cp_before` of moves played from the position, else the average negated
  `eval_cp_after` of moves that reached it. `PLAYED_MOVE` results and
  `avg_eval_after` are from the side that moved.
- **Severity** on stored `cp_loss`: inaccuracy 50, mistake 100, blunder 300.
  Mate scores are stored as +/-10000, so `mate_swing` marks 5,000 cp or more.
- **Material signature** uses the Endgame Atlas notation: White first, each side
  K then Q, R, B, N, P (`KQBvKRN`, `KvKPP`). It equals `endgame_type` for the
  same material.
- **Phase** follows a simplified Lichess divider: endgame when queens, rooks,
  bishops and knights number 6 or fewer; opening when they number more than 10
  and each side has at least 4 pieces on its back rank; middlegame otherwise.
- **Clocks.** The PGN exports have no `%clk` comments, so `clock_rem_sec` is
  empty in PostgreSQL and the graph has no clock fields.

---

## Verification queries

```cypher
// Load metadata
MATCH (m:ChessGraphMeta {name: 'chessgraph'}) RETURN m;

// REACHED = stored moves + one start position per game
MATCH (:Game)-[r:REACHED]->() RETURN count(r);

// Game positions linked to Endgame Atlas hubs
MATCH (p:Position)-[:HAS_ENDGAME_TYPE {from_games: true}]->(e:EndgamePattern)
RETURN e.endgame_type, count(p) AS positions ORDER BY positions DESC LIMIT 10;

// Where your games leave book most often
MATCH (g:Game)-[r:LEFT_THEORY_AT {by: 'owner'}]->(p:Position)
RETURN r.played_san, p.fen_norm, count(g) AS games ORDER BY games DESC LIMIT 10;

// Your moves versus opponents' from the start position
MATCH (:Position {fen_norm: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -'})-[r:PLAYED_MOVE]->()
RETURN r.by, r.san_move, r.games, r.score_pct ORDER BY r.games DESC LIMIT 10;

// Positions where you went wrong in several games
MATCH (p:Position)-[m:MISTAKE_IN]->(g:Game)
WITH p, count(DISTINCT g) AS games, avg(m.cp_loss) AS avg_loss
WHERE games >= 3
RETURN p.fen_norm, games, round(avg_loss) AS avg_loss ORDER BY games DESC LIMIT 10;
```
