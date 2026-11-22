---
name: opening-check
description: Compare Junior's moves with opening theory from a position - where Junior leaves book, what theory plays instead, and how each choice scored. Use for "where do I leave theory", "what do I play against X", "is my move book", or opening repertoire questions.
argument-hint: [FEN or opening name]
---

# Opening check

Request: $ARGUMENTS

1. **Get a FEN.**
   - For "where do I leave theory" with no FEN, call `mcp__plugin_chessgraph_neo4j__get_theory_exits` with `by="owner"` and `limit=5`. Each exit gives the position, Junior's first non-book move, the book moves there (`theory_moves`) and Junior's score. When `book_ended` is true the opening data stops there, so say the book ran out rather than that Junior left it. Check the most frequent exit in the steps below.
   - With an opening name, use `mcp__plugin_chessgraph_postgres__list_games` with the matching `eco_code` to find Junior's games. Take a FEN from `get_game_moves` of one of them.
   - Otherwise start from the initial position: `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -`.
2. **Name the opening.** Call `mcp__plugin_chessgraph_postgres__lookup_opening` on the FEN.
3. **Compare the moves.** Call `mcp__plugin_chessgraph_neo4j__get_position_moves` on the FEN. Split the results into:
   - `THEORY_MOVE`: book moves (`eco_codes` lists the lines);
   - `PLAYED_MOVE` with `by: owner`: Junior's moves, with games, wins/draws/losses and `score_pct` from Junior's side, average centipawn loss and severity counts;
   - `PLAYED_MOVE` with `by: opponent`: what opponents played here, scored from the opponent's side.
4. **Measure a departure.** If Junior's most played move is not a theory move, call `mcp__plugin_chessgraph_stockfish__compare_move` for that move from the same FEN.
5. **Check transpositions.** Call `mcp__plugin_chessgraph_neo4j__find_transpositions` with `max_depth=2` only when the user asks about move orders.

Answer with a short table, then one sentence of advice:

| Move | Book? | Games | Score | Avg CPL |
| --- | --- | --- | --- | --- |
