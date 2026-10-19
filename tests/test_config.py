from chess_mcp.config import clear_settings_cache, get_chess_username, get_stockfish_settings


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


def test_chess_username_prefers_a_resolved_environment_value(monkeypatch) -> None:
    monkeypatch.setenv("CHESS_USERNAME", "from-env")
    monkeypatch.setattr(
        "chess_mcp.config.dotenv_values",
        lambda *_args, **_kwargs: {"CHESS_USERNAME": "from-file"},
    )
    assert get_chess_username() == "from-env"


def test_chess_username_reads_dotenv_when_the_host_forwards_a_placeholder(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHESS_USERNAME", "${CHESS_USERNAME}")
    monkeypatch.setattr(
        "chess_mcp.config.dotenv_values",
        lambda *_args, **_kwargs: {"CHESS_USERNAME": "from-file"},
    )
    assert get_chess_username() == "from-file"
