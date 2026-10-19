from fastapi.testclient import TestClient

from backend.main import create_app
from chess_mcp.postgres.recap import build_recap


class FakePostgres:
    def get_rating_recap(self):
        return build_recap(
            [
                ("2000-plus", "white", "Italian Game", "C50", "win", 1),
                ("2000-plus", "white", "Queen's Pawn Game: London System", "D02", "win", 8),
            ],
            [("2000-plus", "blitz", "win", 9)],
        )

    def get_game(self, game_id: int):
        return None

    def lookup_opening(self, fen: str, *, limit: int = 20):
        return "normalized", []

    def close(self) -> None:
        return None


class MissingGraph:
    def get_position_context(self, fen: str):
        raise LookupError(f"Position is not present in the graph: {fen}")

    def get_position_moves(self, fen: str, limit: int = 20):
        raise AssertionError("context should fail first")

    def close(self) -> None:
        return None


def test_recap_route_returns_the_repository_ranking() -> None:
    client = TestClient(create_app(postgres=FakePostgres()))
    response = client.get("/api/recap")
    assert response.status_code == 200
    band = next(item for item in response.json()["bands"] if item["id"] == "2000-plus")
    assert band["openingsWhite"][0]["name"] == "Queen's Pawn Game: London System"
    assert band["openingsWhite"][1]["name"] == "Italian Game"


def test_missing_game_is_not_found() -> None:
    client = TestClient(create_app(postgres=FakePostgres()))
    response = client.get("/api/games/9")
    assert response.status_code == 404


def test_opening_lookup_uses_the_repository() -> None:
    client = TestClient(create_app(postgres=FakePostgres()))
    response = client.get("/api/openings", params={"fen": "8/8/8/8/8/8/8/K7 w - - 0 1"})
    assert response.status_code == 200
    assert response.json()["openings"] == []


def test_missing_graph_position_is_not_found() -> None:
    client = TestClient(create_app(postgres=FakePostgres(), neo4j=MissingGraph()))
    response = client.get("/api/positions", params={"fen": "8/8/8/8/8/8/8/K7 w - - 0 1"})
    assert response.status_code == 404
    assert "not present" in response.json()["error"]
