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


def test_neo4j_graph_v2_tools_answer_from_the_loaded_graph() -> None:
    """Needs the v2 load: `uv run python etl/neo4j_db/neo4j_load.py --reset`."""
    repository = Neo4jRepository.from_settings(get_neo4j_settings())
    try:
        context = repository.get_position_context(chess.STARTING_FEN)
        assert context.position.phase == "opening"
        assert context.position.visit_games > 0

        moves = repository.get_position_moves(chess.STARTING_FEN, limit=50)
        assert {move.relationship for move in moves.moves} == {"PLAYED_MOVE", "THEORY_MOVE"}
        assert {move.by for move in moves.moves if move.relationship == "PLAYED_MOVE"} <= {"owner", "opponent"}

        through = repository.get_games_through_position(chess.STARTING_FEN, limit=3)
        assert through.total_games == context.position.visit_games
        assert through.owner_wins + through.owner_draws + through.owner_losses <= through.total_games
        assert len(through.games) == 3 and all(visit.ply == 0 for visit in through.games)

        exits = repository.get_theory_exits(limit=5)
        assert exits.exits and all(exit.by == "owner" for exit in exits.exits)

        game_id = through.games[0].game.game_id
        assert repository.get_game_blunders(game_id, min_severity="inaccuracy").game_id == game_id
        assert repository.get_recurring_blunder_positions(limit=3).positions
    finally:
        repository.close()


def test_opponent_plays_a_legal_move_at_limited_strength() -> None:
    from backend.opponent import Opponent

    opponent = Opponent()
    try:
        played = opponent.play(chess.STARTING_FEN, elo=1320, movetime_ms=100)
        assert chess.Move.from_uci(played.uci) in chess.Board().legal_moves
        assert played.elo == 1320
    finally:
        opponent.close()
