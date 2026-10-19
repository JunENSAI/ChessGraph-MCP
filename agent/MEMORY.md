The player is Junior. The Chess.com account name is CHESS_USERNAME in the local .env, not a value stored in this repository. Omit username on lookups so the PostgreSQL server supplies it, then use the username the tool returns.
§
Junior prefers positional chess: pawn structure, weak squares, piece activity, space, outposts, and prophylaxis rather than speculative tactics.
§
ChessGraph is at /home/junior/ChessGraph-MCP. ETL under etl/ writes PostgreSQL and Neo4j. The MCP servers chess_postgres, chess_neo4j, and chess_stockfish are read-only. Evidence order is PostgreSQL, then Neo4j, then Stockfish, then validate_line.
§
The UI coach in ui/src/services/coach.ts is still a demo. HERMES_API_URL and HERMES_API_KEY in .env.template stay empty until the gateway is connected. Do not send HERMES_API_KEY to the browser.
§
Positions use a four-field normalized FEN: piece placement, side to move, castling rights, and en passant. Stockfish needs a six-field FEN built from that key.
