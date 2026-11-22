---
name: status
description: Check that ChessGraph's PostgreSQL, Neo4j and Stockfish are reachable and show their sizes. Use when the user runs /chessgraph:status or a ChessGraph tool fails to connect.
allowed-tools: [Bash]
---

# ChessGraph status

Run this and show the output as is:

```bash
uv run --quiet --directory "${user_config.chessgraph_home}" chessgraph-status
```

If a line says DOWN, suggest the matching fix:

- **postgres:** `systemctl status postgresql`, and check `POSTGRES_*` in the repository `.env`. The password is stored literally there.
- **neo4j:** `~/neo4j-community-*/bin/neo4j status`, and `NEO4J_*` in `.env`.
- **stockfish:** `STOCKFISH_PATH` in `.env`.

To check the MCP servers themselves (tool lists and one call each), run:

```bash
uv run --quiet --directory "${user_config.chessgraph_home}" chessgraph-smoke
```
