---
name: explain-position
description: Explain a chess position for Junior from a FEN - its evaluation, the best move, and the positional reason - and whether it appears in Junior's games or theory. Use when the user pastes a FEN or asks "what should I play here", "who is better", or "why is this move good".
argument-hint: <FEN>
---

# Explain a position

Position: $ARGUMENTS

Follow the chess-coach evidence rules. Steps:

1. In parallel: `mcp__plugin_chessgraph_postgres__get_coaching_brief` and `mcp__plugin_chessgraph_postgres__find_position_occurrences` (Junior's style and whether he reached this position), and `mcp__plugin_chessgraph_neo4j__get_position_moves` (what Junior, his opponents and theory played from it).
2. `mcp__plugin_chessgraph_stockfish__analyze_position` with `multipv=3` and the default depth. If the FEN is rejected, say so and stop.
3. If you will cite more than the engine's own line, run `mcp__plugin_chessgraph_stockfish__validate_line` on the continuation first and quote its SAN.

Answer in three short parts:

- **Position:** score from the side to move and the depth from `limit.value` ("mate in N" for mate scores); "known: N of your games, W/D/L" or "new to your games"; the opening.
- **Lines:** the 3 lines in rank order, each as its first 2-3 SAN moves and its eval. Tag as human the one whose first move Junior's games play most here, else the book move.
- **For you:** one or two sentences tying the choice to Junior's style and record.
