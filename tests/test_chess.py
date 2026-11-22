from chess_mcp.chess import full_fen, normalize_fen


START_FEN_4 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


def test_normalize_fen_drops_move_counters() -> None:
    assert normalize_fen(f"{START_FEN_4} 7 23") == START_FEN_4


def test_full_fen_accepts_project_position_key() -> None:
    assert full_fen(START_FEN_4) == f"{START_FEN_4} 0 1"


def test_normalize_fen_keeps_en_passant_only_when_a_capture_is_legal() -> None:
    after_e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    assert normalize_fen(after_e4).endswith(" b KQkq -")
    capturable = "rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    assert normalize_fen(capturable).endswith(" b KQkq e3")
