---
name: training-plan
description: Tell Junior what to train next from the stored games - strongest and weakest openings, repeated mistakes, and four concrete tasks. Use for "what should I work on", "my weaknesses", "my best opening", or "make me a training plan".
---

# Training plan

1. Call `mcp__plugin_chessgraph_postgres__get_coaching_brief`. Its fields are the whole statement of strengths and weaknesses.
2. Call `mcp__plugin_chessgraph_postgres__get_player_summary` without `username` to give the overall record.
3. Call `mcp__plugin_chessgraph_neo4j__get_recurring_blunder_positions` with `limit=3`: positions where Junior went wrong in two or more games. Use them only as supporting evidence for the target.

Answer with:

- **Record:** games, wins/draws/losses, average rating.
- **Strength:** the top family in `strengths`, with its numbers.
- **Target:** the `target` family with wins/draws/losses, and its most repeated split (played move vs stored engine move, how many times).
- **Four tasks:** each `tasks[i].title` with its `reason`, quoted from the brief.

Then give one move for the task the user asked about. Use `mcp__plugin_chessgraph_stockfish__analyze_position` on that task's `start_fen` with `multipv=1`.

Do not claim an endgame weakness: the brief's `endgames` field says endgame type is not stored on games.
