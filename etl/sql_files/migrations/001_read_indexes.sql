-- Read-path indexes for the MCP tools and the graph ETL. Safe to re-run.
-- Adds indexes only; no table or row is changed.

-- find_position_occurrences matches fen_after_norm as well as fen_before_norm.
CREATE INDEX IF NOT EXISTS idx_moves_fen_after ON game_moves (fen_after_norm);

-- list_games, get_blunders and the coaching brief filter by player name, case-insensitively.
CREATE INDEX IF NOT EXISTS idx_games_white_lower ON games (lower(white_username));
CREATE INDEX IF NOT EXISTS idx_games_black_lower ON games (lower(black_username));
