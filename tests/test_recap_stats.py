from pathlib import Path
import importlib.util

_SCRIPT = Path(__file__).resolve().parents[1] / "ui" / "scripts" / "recap_stats.py"
_SPEC = importlib.util.spec_from_file_location("recap_stats", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
recap_stats = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(recap_stats)


def test_favorite_line_is_the_most_played_stored_name() -> None:
    rows = [
        ("1900-1999", "white", "Italian Game", "C50", "win", 2),
        ("1900-1999", "white", "Italian Game", "C50", "loss", 1),
        ("1900-1999", "white", "Queen's Pawn Game: London System", "D02", "win", 40),
        ("1900-1999", "white", "Queen's Pawn Game: London System", "D02", "loss", 10),
        ("1900-1999", "black", "Scandinavian Defense: Main Line", "B01", "win", 12),
        ("1900-1999", "black", "Caro-Kann Defense", "B10", "win", 5),
    ]
    payload = recap_stats.build_recap(rows, [("1900-1999", "rapid", "win", 70)])
    band = next(item for item in payload["bands"] if item["id"] == "1900-1999")

    assert band["openingsWhite"][0]["name"] == "Queen's Pawn Game: London System"
    assert band["openingsWhite"][0]["results"] == {"wins": 40, "draws": 0, "losses": 10}
    assert band["white"] == {"wins": 42, "draws": 0, "losses": 11}
    assert band["defensesBlack"][0]["name"] == "Scandinavian Defense: Main Line"
    assert band["timeControls"][0]["label"] == "Rapid"
    assert band["openingsWhite"][1]["name"] == "Italian Game"
