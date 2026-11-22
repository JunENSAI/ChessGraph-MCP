from chess_mcp.config import (
    MAX_PATH_DEPTH,
    PROJECT_ROOT,
    base_data_dir,
    clear_settings_cache,
    get_chess_username,
    get_neo4j_settings,
    get_postgres_settings,
    get_stockfish_settings,
    postgres_url,
)


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


def _postgres_env(monkeypatch, password: str) -> None:
    monkeypatch.setenv("POSTGRES_USER", "chess_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "chess")


def test_postgres_url_keeps_reserved_password_characters_literal(monkeypatch) -> None:
    _postgres_env(monkeypatch, "p@ss:w/rd%40")
    url = postgres_url()
    assert url.password == "p@ss:w/rd%40"
    assert url.username == "chess_user"
    assert url.port == 5433
    assert url.database == "chess"
    rendered = url.render_as_string(hide_password=False)
    assert "p%40ss%3Aw%2Frd%2540@127.0.0.1" in rendered


def test_postgres_settings_use_the_escaped_url(monkeypatch) -> None:
    _postgres_env(monkeypatch, "a@b")
    clear_settings_cache()
    settings = get_postgres_settings()
    assert settings.database_url.password == "a@b"
    clear_settings_cache()


def test_neo4j_path_depth_cannot_exceed_the_hard_ceiling(monkeypatch) -> None:
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")
    monkeypatch.setenv("NEO4J_MAX_PATH_DEPTH", "8")
    clear_settings_cache()
    assert get_neo4j_settings().max_path_depth == MAX_PATH_DEPTH == 4
    clear_settings_cache()


def test_base_data_dir_defaults_to_the_repository_data_folder(monkeypatch) -> None:
    monkeypatch.delenv("BASE_DATA_DIR", raising=False)
    monkeypatch.setattr(
        "chess_mcp.config.dotenv_values", lambda *_args, **_kwargs: {}
    )
    assert base_data_dir() == PROJECT_ROOT / "data"
