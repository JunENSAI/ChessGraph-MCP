---
name: review-game
description: Review one of Junior's stored games - the largest mistakes, what Stockfish preferred from the same position, and the lesson. Use when the user asks to review a game, "my last game", "why did I lose", or gives a game id.
argument-hint: [game_id | "last" | game type like rapid]
---

# Review a game

Request: $ARGUMENTS

1. **Find the game.**
   - With a numeric id, call `mcp__plugin_chessgraph_postgres__get_game`.
   - Otherwise call `mcp__plugin_chessgraph_postgres__list_games`, using `limit=1` and the `game_type` if one was named, and take the most recent.
   - Report: date, time control, colour, opponent rating, result and opening.
2. **Find the mistakes.** Call `mcp__plugin_chessgraph_postgres__get_blunders` with that `game_id` and `minimum_cp_loss=100`. Keep the three largest.
3. **For each mistake, in order:**
   - Call `mcp__plugin_chessgraph_stockfish__compare_move` from `fen_before` with the played UCI move, using one depth for all three.
   - Report the played move, the engine move, both scores, and the centipawn loss the tool computed.
   - Name the clock remaining when it is stored.
   - Call `mcp__plugin_chessgraph_neo4j__get_position_moves` on the same FEN to show whether Junior has met this position before.
4. **Validate before quoting.** Run `mcp__plugin_chessgraph_stockfish__validate_line` on any continuation longer than one move first.

Finish with one lesson, the pattern behind the largest mistake, in positional terms. If no mistake of 100 cp or more is stored, say the game has no stored mistake above that threshold.
