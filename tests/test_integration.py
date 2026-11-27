"""Opt-in smoke tests for locally configured services."""

from __future__ import annotations

import os

import chess
import pytest

from chess_mcp.config import (
    get_chess_username,
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


def test_opening_lessons_count_results_from_the_player_side() -> None:
    """The W/D/L columns compare the game_result enum, and never exceed the games."""
    repository = PostgresRepository.from_settings(get_postgres_settings())
    try:
        for color in ("white", "black"):
            lessons = repository.list_opening_lessons(player=get_chess_username(), color=color, limit=5)
            for lesson in lessons:
                assert lesson.wins + lesson.draws + lesson.losses <= lesson.games
            if lessons:
                assert sum(lesson.wins + lesson.draws + lesson.losses for lesson in lessons) > 0
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


GRAPH_COUNTS = """
CALL () { MATCH (g:Game) RETURN count(g) AS games }
CALL () { MATCH (:Game)-[r:REACHED]->() RETURN count(r) AS reached }
CALL () { MATCH ()-[r:PLAYED_MOVE {by: 'owner'}]->() RETURN sum(r.times) AS owner_moves }
CALL () { MATCH ()-[r:PLAYED_MOVE {by: 'opponent'}]->() RETURN sum(r.times) AS opponent_moves }
CALL () {
  MATCH ()-[r:PLAYED_MOVE]->() WHERE r.wins + r.draws + r.losses <> r.games OR coalesce(r.games, 0) = 0
  RETURN count(r) AS bad_results
}
CALL () {
  MATCH ()-[m:MISTAKE_IN]->()
  RETURN sum(CASE WHEN m.cp_loss < 100 THEN 1 ELSE 0 END) AS inaccuracies,
         sum(CASE WHEN m.cp_loss >= 100 AND m.cp_loss < 300 THEN 1 ELSE 0 END) AS mistakes,
         sum(CASE WHEN m.cp_loss >= 300 THEN 1 ELSE 0 END) AS blunders
}
CALL () { MATCH (p:Player {is_owner: true}) RETURN count(p) AS owners }
RETURN games, reached, owner_moves, opponent_moves, bad_results, inaccuracies, mistakes, blunders, owners
"""

POSTGRES_COUNTS = """
SELECT (SELECT count(*) FROM games) AS games,
       count(*) AS moves,
       count(*) FILTER (WHERE owner) AS owner_moves,
       count(*) FILTER (WHERE NOT owner) AS opponent_moves,
       count(*) FILTER (WHERE owner AND cp_loss >= 50 AND cp_loss < 100) AS inaccuracies,
       count(*) FILTER (WHERE owner AND cp_loss >= 100 AND cp_loss < 300) AS mistakes,
       count(*) FILTER (WHERE owner AND cp_loss >= 300) AS blunders
FROM (
  SELECT m.turn_color::text = left(g.user_color::text, 1) AS owner, m.cp_loss  -- w/b vs white/black
  FROM game_moves m JOIN games g USING (game_id)
) AS moves
"""


def test_neo4j_graph_agrees_with_postgres() -> None:
    """The graph is a faithful projection of the stored games (run after a --reset load)."""
    from sqlalchemy import create_engine, text

    from chess_mcp.config import postgres_url

    engine = create_engine(postgres_url())
    repository = Neo4jRepository.from_settings(get_neo4j_settings())
    try:
        with engine.connect() as connection:
            pg = dict(connection.execute(text(POSTGRES_COUNTS)).mappings().one())
        graph = repository._read(GRAPH_COUNTS, {})[0]
    finally:
        repository.close()
        engine.dispose()

    assert graph["games"] == pg["games"]
    assert graph["reached"] == pg["moves"] + pg["games"]  # every move plus one start per game
    assert graph["owner_moves"] == pg["owner_moves"]
    assert graph["opponent_moves"] == pg["opponent_moves"]
    assert graph["bad_results"] == 0
    assert (graph["inaccuracies"], graph["mistakes"], graph["blunders"]) == (
        pg["inaccuracies"], pg["mistakes"], pg["blunders"],
    )
    assert graph["owners"] == 1


def test_style_context_reads_the_owner_record_around_the_start() -> None:
    repository = Neo4jRepository.from_settings(get_neo4j_settings())
    try:
        context = repository.get_style_context(chess.STARTING_FEN)
    finally:
        repository.close()
    assert context.owner_moves and all(move.by == "owner" for move in context.owner_moves)
    assert context.theory_moves and all(move.relationship == "THEORY_MOVE" for move in context.theory_moves)
    assert context.total_games == context.owner_wins + context.owner_draws + context.owner_losses
    assert all(item.distance <= context.depth for item in context.nearby_mistakes)

def test_opponent_plays_a_legal_move_at_limited_strength() -> None:
    from backend.opponent import Opponent

    opponent = Opponent()
    try:
        played = opponent.play(chess.STARTING_FEN, elo=1320, movetime_ms=100)
        assert chess.Move.from_uci(played.uci) in chess.Board().legal_moves
        assert played.elo == 1320
    finally:
        opponent.close()
