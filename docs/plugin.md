# Claude Code plugin

`plugins/chessgraph/` packages ChessGraph for Claude Code. It replaces the old
Hermes-Agent setup. The in-app coach is separate: it runs in the API (`backend/coach/`).

```text
plugins/chessgraph/
├── .claude-plugin/plugin.json   name, version, userConfig.chessgraph_home
├── .mcp.json                    postgres, neo4j, stockfish (stdio, via uv)
├── agents/chess-coach.md        persona + evidence rules, MCP tools only
├── skills/
│   ├── explain-position/        /chessgraph:explain-position <FEN>
│   ├── review-game/             /chessgraph:review-game [id|last|rapid…]
│   ├── training-plan/           /chessgraph:training-plan
│   ├── opening-check/           /chessgraph:opening-check [FEN]
│   └── status/                  /chessgraph:status
└── README.md
```

The repository root holds `.claude-plugin/marketplace.json`, so the checkout is
also a local marketplace.

## Install

```bash
claude plugin marketplace add /path/to/ChessGraph-MCP
claude plugin install chessgraph@chessgraph
```

Set `chessgraph_home` when Claude Code asks for it, or with
`/plugin configure chessgraph@chessgraph`. It is the absolute path of the
checkout. A marketplace added from a local path loads the plugin in place, so
edits to the skills apply after a restart.

To try a change without installing, run `claude --plugin-dir plugins/chessgraph`
for that session only. `chessgraph_home` is then unset, so the MCP servers
cannot start. Use the installed plugin to test the tools.

## How the servers start

Each server is launched as:

```text
uv run --quiet --directory ${user_config.chessgraph_home} chessgraph-<name>-mcp
```

- `uv` must be on `PATH`.
- `--directory` makes the server run from the checkout, so `chess_mcp.config`
  reads the repository `.env`. Credentials never enter the plugin.
- Tool names follow `mcp__plugin_chessgraph_<server>__<tool>`, for example
  `mcp__plugin_chessgraph_stockfish__compare_move`. The `chess-coach` agent
  limits itself to these three tool sets.

## Testing without a model

None of these calls a language model or needs an API key.

| Check | Command |
| --- | --- |
| Manifests and frontmatter | `claude plugin validate plugins/chessgraph` and `claude plugin validate .` |
| Services reachable | `uv run chessgraph-status` |
| Servers over stdio, tool contract, one call each | `uv run chessgraph-smoke` |
| Claude Code starts the plugin's servers | install the plugin, then `claude mcp list` |
| Unit tests | `uv run pytest tests/test_status_and_smoke.py` |

To run the `claude mcp list` check without touching your own settings, give
Claude Code a throwaway config folder:

```bash
export CLAUDE_CONFIG_DIR=$(mktemp -d)
claude plugin marketplace add "$PWD"
claude plugin install chessgraph@chessgraph
echo "{\"chessgraph_home\": \"$PWD\"}" | claude plugin configure chessgraph@chessgraph --values-stdin
claude mcp list        # expect three "✔ Connected" lines
```

## Ideas for later

- A `SessionStart` hook that runs `chessgraph-status` and warns when a store is
  down.
- An eval suite (`claude plugin eval`) with fixed positions and graders that
  check every cited move against `validate_line`.
- Skills for the graph tools added in the Neo4j batch, such as theory exits and
  games through a position.
