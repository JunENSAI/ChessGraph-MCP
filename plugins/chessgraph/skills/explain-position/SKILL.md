---
name: explain-position
description: Explain a chess position for Junior from a FEN - its evaluation, the best move, and the positional reason - and whether it appears in Junior's games or theory. Use when the user pastes a FEN or asks "what should I play here", "who is better", or "why is this move good".
argument-hint: <FEN>
---

# Explain a position

Position: $ARGUMENTS

Follow the chess-coach evidence rules. Steps:

1. `mcp__plugin_chessgraph_stockfish__analyze_position` with `multipv=1` and the default depth. If the FEN is rejected, say so and stop.
2. In parallel, `mcp__plugin_chessgraph_postgres__find_position_occurrences` and `mcp__plugin_chessgraph_neo4j__get_position_moves` for the same FEN: has Junior reached this position, and what did Junior and theory play from it?
3. If you will cite more than the first move, run `mcp__plugin_chessgraph_stockfish__validate_line` on the continuation first and quote its SAN.

Answer with:

- **Evaluation:** score from the side to move, and the depth from `limit.value`. Say "mate in N" for mate scores.
- **Move:** one move in SAN.
- **Why:** at most two sentences, positional terms first.
- **Your history:** one line. Give the number of games and what Junior played, or "not in your games".
