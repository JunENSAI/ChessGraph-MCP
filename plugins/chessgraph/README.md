# chessgraph plugin

Chess coaching in Claude Code, grounded in your own games. The plugin bundles:

- three read-only MCP servers: PostgreSQL games, the Neo4j position graph, and
  Stockfish;
- the `chess-coach` agent;
- the skills `explain-position`, `review-game`, `training-plan`,
  `opening-check`, and `status`.

It needs a ChessGraph-MCP checkout with a filled `.env`, and `uv` on `PATH`.
Set `chessgraph_home` to that checkout when Claude Code asks for it.

```bash
claude plugin marketplace add /path/to/ChessGraph-MCP
claude plugin install chessgraph@chessgraph
```

Full guide: `docs/plugin.md` in the repository.
