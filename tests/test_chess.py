from chess_mcp.chess import full_fen, normalize_fen


START_FEN_4 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


def test_normalize_fen_drops_move_counters() -> None:
    assert normalize_fen(f"{START_FEN_4} 7 23") == START_FEN_4


def test_full_fen_accepts_project_position_key() -> None:
    assert full_fen(START_FEN_4) == f"{START_FEN_4} 0 1"
