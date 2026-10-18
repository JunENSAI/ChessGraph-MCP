import pytest

from chess_mcp.chess import full_fen, normalize_fen, replay_uci_line


START_FEN_4 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


def test_normalize_fen_drops_move_counters() -> None:
    assert normalize_fen(f"{START_FEN_4} 7 23") == START_FEN_4


def test_full_fen_accepts_project_position_key() -> None:
    assert full_fen(START_FEN_4) == f"{START_FEN_4} 0 1"


def test_replay_uci_line_returns_legal_san_and_final_fen() -> None:
    uci, san, final_fen = replay_uci_line(START_FEN_4, ["e2e4", "e7e5"])
    assert uci == ["e2e4", "e7e5"]
    assert san == ["e4", "e5"]
    assert final_fen.split()[1] == "w"


def test_replay_uci_line_rejects_illegal_move() -> None:
    with pytest.raises(ValueError, match="Illegal UCI move"):
        replay_uci_line(START_FEN_4, ["e2e5"])
