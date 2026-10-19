# Install

Copy these seeds into the Hermes home only when the destination is missing. This repository does not write `~/.hermes`.

- `agent/SOUL.md` → `~/.hermes/SOUL.md`
- `agent/MEMORY.md` → `~/.hermes/memories/MEMORY.md`
- `agent/USER.md` → `~/.hermes/memories/USER.md`

```bash
mkdir -p ~/.hermes/memories
cp -n agent/SOUL.md ~/.hermes/SOUL.md
cp -n agent/MEMORY.md ~/.hermes/memories/MEMORY.md
cp -n agent/USER.md ~/.hermes/memories/USER.md
```

`cp -n` leaves an existing file untouched. `MEMORY.md` and `USER.md` are Hermes entries separated by `§`. Merge `hermes-mcp.example.yaml` into `~/.hermes/config.yaml` on its own. Project instructions stay in the repository root `AGENTS.md`, which Hermes loads when this directory is the working directory.

The Chess.com account name stays in the local `.env` as `CHESS_USERNAME`. Do not copy it into these seeds.
