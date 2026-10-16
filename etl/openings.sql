-- Openings in a Parquet file that can be downloaded from Hugging Face

CREATE TABLE opening_theory (
    opening_id       SERIAL PRIMARY KEY,
    eco_volume       CHAR(1),
    eco_code         VARCHAR(10) NOT NULL,
    opening_name     TEXT NOT NULL,
    pgn_line         TEXT NOT NULL,
    uci_line         TEXT,
    epd_norm         TEXT NOT NULL
);

CREATE INDEX idx_opening_epd ON opening_theory(epd_norm);
CREATE INDEX idx_opening_eco ON opening_theory(eco_code);