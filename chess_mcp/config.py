"""Validated runtime configuration for the three local MCP servers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from sqlalchemy import URL


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


# Hard ceiling for graph traversals. NEO4J_MAX_PATH_DEPTH may lower it, never raise it.
MAX_PATH_DEPTH = 4


class ConfigurationError(ValueError):
    """Raised when required server configuration is missing or invalid."""


_UNEXPANDED = re.compile(r"^\$\{[^}]+\}$")


def _optional(name: str, default: str = "") -> str:
    """Return a variable from the environment, then the project ``.env``.

    An empty value or an unexpanded ``${NAME}`` placeholder is ignored so a
    host that forwards the variable without resolving it does not hide the
    project ``.env`` entry.
    """
    value = os.getenv(name, "").strip()
    if value and _UNEXPANDED.fullmatch(value) is None:
        return value
    file_value = (dotenv_values(PROJECT_ROOT / ".env").get(name) or "").strip()
    if file_value and _UNEXPANDED.fullmatch(file_value) is None:
        return file_value
    return default


def get_setting(name: str, default: str = "") -> str:
    """Public read of one optional setting, for ETL scripts."""
    return _optional(name, default)


def get_int_setting(name: str, default: int) -> int:
    """Public read of one positive integer setting, for ETL scripts."""
    return _integer(name, default)


def get_chess_username() -> str:
    """Return the Chess.com account from CHESS_USERNAME, then the local .env."""
    return _optional("CHESS_USERNAME")


def _required(name: str) -> str:
    value = _optional(name)
    if not value:
        raise ConfigurationError(f"Required environment variable {name} is not set")
    return value


def _integer(name: str, default: int, *, minimum: int = 1) -> int:
    raw = _optional(name)
    try:
        value = default if not raw else int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    database_url: URL
    statement_timeout_ms: int
    max_results: int


@dataclass(frozen=True, slots=True)
class Neo4jSettings:
    uri: str
    user: str
    password: str
    database: str
    max_results: int
    max_path_depth: int


@dataclass(frozen=True, slots=True)
class StockfishSettings:
    path: Path
    default_depth: int
    max_depth: int
    max_nodes: int
    max_time_ms: int
    max_multipv: int
    threads: int
    hash_mb: int


def postgres_url() -> URL:
    """Build the PostgreSQL URL from the raw .env values.

    ``URL.create`` escapes reserved characters itself, so ``POSTGRES_PASSWORD``
    holds the literal password (an ``@`` stays an ``@``), the same value psql
    and DBeaver use.
    """
    return URL.create(
        "postgresql+psycopg2",
        username=_required("POSTGRES_USER"),
        password=_required("POSTGRES_PASSWORD"),
        host=_optional("POSTGRES_HOST", "127.0.0.1"),
        port=_integer("POSTGRES_PORT", 5432),
        database=_required("POSTGRES_DB"),
    )


def base_data_dir() -> Path:
    """Return the ETL data folder: BASE_DATA_DIR, or ``data/`` in the repository."""
    return Path(_optional("BASE_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()


@lru_cache(maxsize=1)
def get_postgres_settings() -> PostgresSettings:
    return PostgresSettings(
        database_url=postgres_url(),
        statement_timeout_ms=_integer("POSTGRES_STATEMENT_TIMEOUT_MS", 10_000),
        max_results=_integer("MCP_MAX_RESULTS", 100),
    )


@lru_cache(maxsize=1)
def get_neo4j_settings() -> Neo4jSettings:
    return Neo4jSettings(
        uri=_optional("NEO4J_URI", "bolt://127.0.0.1:7687"),
        user=_required("NEO4J_USER"),
        password=_required("NEO4J_PASSWORD"),
        database=_optional("NEO4J_DATABASE", "neo4j"),
        max_results=_integer("MCP_MAX_RESULTS", 100),
        max_path_depth=min(_integer("NEO4J_MAX_PATH_DEPTH", 4), MAX_PATH_DEPTH),
    )


@lru_cache(maxsize=1)
def get_stockfish_settings() -> StockfishSettings:
    legacy_depth = _integer("STOCKFISH_DEPTH", 15)
    default_depth = _integer(
        "STOCKFISH_DEFAULT_DEPTH",
        legacy_depth,
    )
    max_depth = _integer("STOCKFISH_MAX_DEPTH", 30)
    if default_depth > max_depth:
        raise ConfigurationError(
            "STOCKFISH_DEFAULT_DEPTH cannot exceed STOCKFISH_MAX_DEPTH"
        )
    return StockfishSettings(
        path=Path(_optional("STOCKFISH_PATH", "/usr/games/stockfish")).expanduser(),
        default_depth=default_depth,
        max_depth=max_depth,
        max_nodes=_integer("STOCKFISH_MAX_NODES", 5_000_000),
        max_time_ms=_integer("STOCKFISH_MAX_TIME_MS", 30_000),
        max_multipv=min(_integer("STOCKFISH_MAX_MULTIPV", 5), 20),
        threads=_integer("STOCKFISH_THREADS", 1),
        hash_mb=_integer("STOCKFISH_HASH_MB", 128),
    )


def clear_settings_cache() -> None:
    """Clear cached settings, primarily for tests."""
    get_postgres_settings.cache_clear()
    get_neo4j_settings.cache_clear()
    get_stockfish_settings.cache_clear()
