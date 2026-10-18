"""Opt-in smoke tests for locally configured services."""

from __future__ import annotations

import os

import chess
import pytest

from chess_mcp.config import (
    get_neo4j_settings,
    get_postgres_settings,
    get_stockfish_settings,
)
from chess_mcp.neo4j.repository import Neo4jRepository
from chess_mcp.postgres.repository import PostgresRepository
from chess_mcp.stockfish.engine import StockfishService


pytestmark = pytest.mark.skipif(
    os.getenv("CHESSGRAPH_RUN_INTEGRATION") != "1",
    reason="set CHESSGRAPH_RUN_INTEGRATION=1 to test local services",
)


def test_postgres_read_connection() -> None:
    repository = PostgresRepository.from_settings(get_postgres_settings())
    try:
        repository.list_games(limit=1)
    finally:
        repository.close()


def test_neo4j_read_connection() -> None:
    repository = Neo4jRepository.from_settings(get_neo4j_settings())
    try:
        repository._driver.verify_connectivity()
        repository.get_position_moves(chess.STARTING_FEN, limit=1)
    finally:
        repository.close()


def test_stockfish_connection() -> None:
    assert get_stockfish_settings().path.exists()
    service = StockfishService()
    try:
        result = service.analyze_position(
            chess.STARTING_FEN,
            limit_type="depth",
            limit_value=1,
            multipv=1,
        )
        assert result.lines
    finally:
        service.close()
