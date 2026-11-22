"""Strength-limited opponent engine and the play/explorer routes, with fakes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import chess
import chess.engine
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.opponent import Opponent, PlayedMove
from chess_mcp.neo4j.models import GamesThroughPosition, PositionMoves

START = chess.STARTING_FEN


class FakeEngine:
    def __init__(self, move: str = "e2e4", score: chess.engine.PovScore | None = None) -> None:
        self.move = move
        self.score = score
        self.calls: list[dict[str, Any]] = []
        self.quit_called = False

    def play(self, board: chess.Board, limit: chess.engine.Limit, *, info: Any, options: dict[str, object]):
        self.calls.append({"fen": board.fen(), "time": limit.time, "options": options})
        return SimpleNamespace(move=chess.Move.from_uci(self.move), info={"score": self.score} if self.score else {})

    def quit(self) -> None:
        self.quit_called = True


def test_limited_strength_sets_the_uci_options_and_reports_the_movers_score() -> None:
    fake = FakeEngine("e7e5", chess.engine.PovScore(chess.engine.Cp(-40), chess.WHITE))
    opponent = Opponent(engine_factory=lambda _path: fake)
    board = chess.Board()
    board.push_uci("e2e4")

    played = opponent.play(board.fen(), elo=1500, movetime_ms=200)

    assert fake.calls[0]["options"] == {"UCI_LimitStrength": True, "UCI_Elo": 1500}
    assert fake.calls[0]["time"] == 0.2
    assert (played.uci, played.san) == ("e7e5", "e5")
    # White's -40 is Black's +40: the score is from the side that moved.
    assert (played.score_type, played.score_value) == ("cp", 40)
    assert played.fen.startswith("rnbqkbnr/pppp1ppp/8/4p3/4P3/")
    opponent.close()
    assert fake.quit_called


def test_full_strength_turns_the_limit_off() -> None:
    fake = FakeEngine("e2e4", chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE))
    played = Opponent(engine_factory=lambda _path: fake).play(START, elo=None, movetime_ms=100)
    assert fake.calls[0]["options"] == {"UCI_LimitStrength": False}
    assert (played.score_type, played.score_value) == ("mate", 3)


@pytest.mark.parametrize(
    ("fen", "elo", "movetime", "message"),
    [
        ("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3", 1500, 100, "game is over"),
        (START, 900, 100, "elo must be between"),
        (START, 1500, 10, "movetime_ms"),
    ],
)
def test_invalid_requests_never_reach_the_engine(fen: str, elo: int, movetime: int, message: str) -> None:
    fake = FakeEngine()
    with pytest.raises(ValueError, match=message):
        Opponent(engine_factory=lambda _path: fake).play(fen, elo=elo, movetime_ms=movetime)
    assert fake.calls == []


def test_an_illegal_engine_move_is_rejected() -> None:
    with pytest.raises(ValueError, match="no legal move"):
        Opponent(engine_factory=lambda _path: FakeEngine("e2e5")).play(START, elo=None, movetime_ms=100)


class FakeOpponent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None, int]] = []

    def play(self, fen: str, elo: int | None, movetime_ms: int) -> PlayedMove:
        self.calls.append((fen, elo, movetime_ms))
        return PlayedMove(uci="e2e4", san="e4", fen="after", elo=elo, score_type="cp", score_value=30)

    def close(self) -> None:
        return None


class NoPostgres:
    def close(self) -> None:
        return None


def test_play_route_validates_and_delegates() -> None:
    opponent = FakeOpponent()
    client = TestClient(create_app(postgres=NoPostgres(), opponent=opponent))  # type: ignore[arg-type]

    response = client.post("/api/engine/play", json={"fen": START, "elo": 1600})
    assert response.status_code == 200
    assert response.json()["san"] == "e4"
    assert opponent.calls == [(START, 1600, 300)]

    assert client.post("/api/engine/play", json={"fen": START, "elo": 4000}).status_code == 422
    assert client.post("/api/engine/play", json={"fen": START, "movetime_ms": 99999}).status_code == 422
    assert client.post("/api/engine/play", json={"fen": START, "elo": None}).status_code == 200
    assert opponent.calls[-1] == (START, None, 300)


class ExplorerGraph:
    def __init__(self, known: bool) -> None:
        self.known = known

    def get_position_context(self, fen: str):
        if not self.known:
            raise LookupError("Position is not present in the graph")
        return {"position": {"fen_norm": "start"}}

    def get_position_moves(self, fen: str, limit: int = 20):
        assert limit == 30
        return PositionMoves(fen_norm="start", moves=[])

    def get_games_through_position(self, fen: str, limit: int = 20):
        return GamesThroughPosition(fen_norm="start", total_games=0)

    def close(self) -> None:
        return None


def test_explorer_answers_an_unknown_position_with_empty_context() -> None:
    client = TestClient(create_app(postgres=NoPostgres(), neo4j=ExplorerGraph(known=False)))  # type: ignore[arg-type]
    response = client.get("/api/explorer", params={"fen": START})
    assert response.status_code == 200
    body = response.json()
    assert body["context"] is None and body["moves"] == [] and body["games"]["total_games"] == 0

    known = TestClient(create_app(postgres=NoPostgres(), neo4j=ExplorerGraph(known=True)))  # type: ignore[arg-type]
    assert known.get("/api/explorer", params={"fen": START}).json()["context"]["position"]["fen_norm"] == "start"
