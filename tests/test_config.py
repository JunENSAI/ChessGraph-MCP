from chess_mcp.config import clear_settings_cache, get_stockfish_settings


def test_stockfish_settings_honor_bounds(monkeypatch) -> None:
    monkeypatch.setenv("STOCKFISH_DEFAULT_DEPTH", "18")
    monkeypatch.setenv("STOCKFISH_MAX_DEPTH", "24")
    monkeypatch.setenv("STOCKFISH_MAX_MULTIPV", "3")
    clear_settings_cache()
    settings = get_stockfish_settings()
    assert settings.default_depth == 18
    assert settings.max_depth == 24
    assert settings.max_multipv == 3
    clear_settings_cache()
