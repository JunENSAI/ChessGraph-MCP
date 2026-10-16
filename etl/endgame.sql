-- The Endgame csv file can be downloaded from Hugging Face

CREATE TABLE endgame_theory (
    endgame_id       BIGSERIAL PRIMARY KEY,
    fen_full         TEXT NOT NULL, 
    fen_norm         TEXT NOT NULL,
    human_move_uci   VARCHAR(10) NOT NULL,
    endgame_type     VARCHAR(30) NOT NULL,
    piece_count      SMALLINT NOT NULL,
    time_control     VARCHAR(20),
    player_elo       INTEGER,
    opp_elo          INTEGER,
    elo_tier         VARCHAR(20)
);

-- Indexes so the Coach Agent can filter by material signature, piece count, or ELO tier
CREATE INDEX idx_endgame_type_tier ON endgame_theory(endgame_type, elo_tier);
CREATE INDEX idx_endgame_pieces    ON endgame_theory(piece_count);
CREATE INDEX idx_endgame_fen_norm  ON endgame_theory(fen_norm);