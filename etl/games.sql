DROP VIEW IF EXISTS v_blitz_games, v_rapid_games, v_bullet_games, v_daily_games, v_bot_games CASCADE;
DROP TABLE IF EXISTS game_moves CASCADE;
DROP TABLE IF EXISTS games CASCADE;

-- ============================================================================
-- 1. ENUM TYPES
-- ============================================================================
DO $$ BEGIN
    CREATE TYPE game_category AS ENUM ('rapid', 'blitz', 'bullet', 'daily', 'bot');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE game_result AS ENUM ('1-0', '0-1', '1/2-1/2', '*');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- 2. GAMES (Mapped to Chess.com PGN Headers)
-- ============================================================================
CREATE TABLE games (
    game_id          BIGSERIAL PRIMARY KEY,
    game_hash        VARCHAR(64) UNIQUE NOT NULL,
    game_type        game_category NOT NULL,
    
    -- PGN Header Fields
    event            VARCHAR(100) DEFAULT 'Live Chess',
    site             VARCHAR(50)  DEFAULT 'Chess.com',
    played_date      DATE NOT NULL,
    end_time_utc     TIME,
    round            VARCHAR(20)  DEFAULT '-',
    
    -- Players & Ratings
    white_username   VARCHAR(100) NOT NULL,
    black_username   VARCHAR(100) NOT NULL,
    white_elo        INTEGER,
    black_elo        INTEGER,
    
    -- Perspective Helper Columns (for Junior_MG01)
    user_color       CHAR(5) CHECK (user_color IN ('white', 'black')),
    user_elo         INTEGER,
    opponent_elo     INTEGER,
    user_outcome     VARCHAR(10) CHECK (user_outcome IN ('win', 'loss', 'draw', 'other')),
    
    -- Result & Time Control
    result           game_result NOT NULL,
    time_control_raw VARCHAR(50) NOT NULL,
    base_time_sec    INTEGER,
    increment_sec    INTEGER DEFAULT 0,
    termination      TEXT,
    
    -- Opening & Raw PGN
    eco_code         VARCHAR(10),
    opening_name     TEXT,
    total_plies      INTEGER,
    pgn_moves_raw    TEXT NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast MCP Agent queries
CREATE INDEX idx_games_type_date    ON games(game_type, played_date DESC);
CREATE INDEX idx_games_user_outcome ON games(game_type, user_color, user_outcome);
CREATE INDEX idx_games_eco          ON games(eco_code);

-- ============================================================================
-- 3. MOVE-BY-MOVE TABLE (Links Postgres to Neo4j FENs & Stockfish)
-- ============================================================================
CREATE TABLE game_moves (
    move_id          BIGSERIAL PRIMARY KEY,
    game_id          BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    ply_number       INTEGER NOT NULL,
    move_number      INTEGER NOT NULL,
    turn_color       CHAR(1) NOT NULL CHECK (turn_color IN ('w', 'b')),
    
    san_move         VARCHAR(20) NOT NULL,
    uci_move         VARCHAR(10) NOT NULL,
    fen_before_norm  TEXT NOT NULL,
    fen_after_norm   TEXT NOT NULL,
    
    clock_rem_sec    NUMERIC(8, 2),
    eval_cp_before   INTEGER,
    eval_cp_after    INTEGER,
    cp_loss          INTEGER,
    best_move_uci    VARCHAR(10),
    
    UNIQUE (game_id, ply_number)
);

CREATE INDEX idx_moves_game_ply ON game_moves(game_id, ply_number);
CREATE INDEX idx_moves_fen      ON game_moves(fen_before_norm);

CREATE OR REPLACE VIEW v_blitz_games  AS SELECT * FROM games WHERE game_type = 'blitz';
CREATE OR REPLACE VIEW v_rapid_games  AS SELECT * FROM games WHERE game_type = 'rapid';
CREATE OR REPLACE VIEW v_bullet_games AS SELECT * FROM games WHERE game_type = 'bullet';
CREATE OR REPLACE VIEW v_daily_games  AS SELECT * FROM games WHERE game_type = 'daily';
CREATE OR REPLACE VIEW v_bot_games    AS SELECT * FROM games WHERE game_type = 'bot';