from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.main import create_app
from chess_mcp.postgres.models import EndgameLesson, GameMove, GameSummary, OpeningLesson, PlayerSummary
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
    assert band["openingsWhite"][0]["name"] == "London System"
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


class LessonPostgres(FakePostgres):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_games(self, **arguments: object):
        self.calls.append(("list_games", arguments))
        return []

    def list_opening_lessons(self, **arguments: object):
        self.calls.append(("openings", arguments))
        return [
            OpeningLesson(
                opening_name="Italian Game",
                eco_code="C50",
                games=12,
                uci_line="e2e4 e7e5",
                pgn_line="1. e4 e5",
            )
        ]

    def get_player_summary(self, username: str, game_type: str | None = None):
        return PlayerSummary(
            username=username,
            games_played=12,
            wins=6,
            losses=4,
            draws=2,
            unfinished=0,
            average_rating=1760,
        )

    def list_endgame_lessons(self, **arguments: object):
        self.calls.append(("endgames", arguments))
        return (
            "1600-1800",
            [
                EndgameLesson(
                    endgame_type="rook_pawn",
                    fen_full="8/8/8/8/8/2k5/8/K6R w - - 0 1",
                    human_move_uci="h1h2",
                    elo_tier="1600-1800",
                    piece_count=3,
                )
            ],
        )


def test_opening_lessons_use_the_requested_color() -> None:
    client = TestClient(create_app(postgres=LessonPostgres()))
    response = client.get("/api/lessons/openings", params={"color": "black", "player": "junior"})
    assert response.status_code == 200
    body = response.json()
    assert body["lessons"][0]["opening_name"] == "Italian Game"
    assert body["lessons"][0]["uci_line"] == "e2e4 e7e5"


def test_endgame_lessons_use_the_player_rating() -> None:
    postgres = LessonPostgres()
    client = TestClient(create_app(postgres=postgres))
    response = client.get("/api/lessons/endgames", params={"player": "junior"})
    assert response.status_code == 200
    body = response.json()
    assert body["elo_tier"] == "1600-1800"
    assert body["lessons"][0]["human_move_uci"] == "h1h2"
    assert postgres.calls[0][1]["average_rating"] == 1760


def test_games_default_to_the_configured_player(monkeypatch) -> None:
    postgres = LessonPostgres()
    monkeypatch.setattr("backend.main.get_chess_username", lambda: "junior")
    client = TestClient(create_app(postgres=postgres))
    response = client.get("/api/games", params={"game_type": "rapid", "limit": 25, "offset": 25})
    assert response.status_code == 200
    assert response.json() == {"games": []}
    arguments = postgres.calls[0][1]
    assert arguments["player"] == "junior"
    assert arguments["offset"] == 25
    assert arguments["limit"] == 25
    assert arguments["game_type"] == "rapid"


class LibraryPostgres(FakePostgres):
    def list_games(self, **arguments: object):
        self.arguments = arguments
        return [
            GameSummary(
                game_id=4,
                game_hash="synthetic",
                game_type="rapid",
                played_date=date(2026, 4, 2),
                white_username="white",
                black_username="black",
                white_elo=1500,
                black_elo=1480,
                result="1-0",
                time_control_raw="600",
                eco_code="C50",
                opening_name="Italian Game",
            )
        ]

    def get_game_moves(self, game_id: int, *, start_ply: int = 1, limit: int = 100):
        self.move_call = (game_id, start_ply, limit)
        return [
            GameMove(
                move_id=9,
                game_id=game_id,
                ply_number=start_ply,
                move_number=1,
                turn_color="w",
                san_move="e4",
                uci_move="e2e4",
                fen_before_norm="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -",
                fen_after_norm="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -",
                eval_cp_after=20,
                cp_loss=0,
                best_move_uci="e2e4",
            )
        ]


class EmptyLessons(FakePostgres):
    def list_opening_lessons(self, **arguments: object):
        return []


class DownPostgres(FakePostgres):
    def list_opening_lessons(self, **arguments: object):
        raise SQLAlchemyError("connection refused")


def test_games_list_serializes_summaries(monkeypatch) -> None:
    postgres = LibraryPostgres()
    monkeypatch.setattr("backend.main.get_chess_username", lambda: "white")
    client = TestClient(create_app(postgres=postgres))
    response = client.get("/api/games", params={"game_type": "rapid", "limit": 25})
    assert response.status_code == 200
    game = response.json()["games"][0]
    assert game["game_id"] == 4
    assert game["played_date"] == "2026-04-02"
    assert game["opening_name"] == "Italian Game"
    assert game["white_username"] == "white"
    assert game["black_username"] == "black"
    assert postgres.arguments["player"] == "white"
    assert postgres.arguments["limit"] == 25


def test_game_moves_keep_the_stored_evaluation() -> None:
    postgres = LibraryPostgres()
    client = TestClient(create_app(postgres=postgres))
    response = client.get("/api/games/4/moves", params={"start_ply": 1, "limit": 100})
    assert response.status_code == 200
    body = response.json()
    assert body["game_id"] == 4
    assert body["start_ply"] == 1
    assert body["moves"][0]["san_move"] == "e4"
    assert body["moves"][0]["uci_move"] == "e2e4"
    assert body["moves"][0]["cp_loss"] == 0
    assert body["moves"][0]["best_move_uci"] == "e2e4"
    assert postgres.move_call == (4, 1, 100)


def test_game_page_size_is_bounded() -> None:
    client = TestClient(create_app(postgres=FakePostgres()))
    assert client.get("/api/games", params={"limit": 101, "player": "white"}).status_code == 422
    assert client.get("/api/games/4/moves", params={"limit": 101}).status_code == 422
    assert client.get("/api/games", params={"offset": 100_001, "player": "white"}).status_code == 422


def test_games_require_a_configured_player(monkeypatch) -> None:
    postgres = LessonPostgres()
    monkeypatch.setattr("backend.main.get_chess_username", lambda: "  ")
    client = TestClient(create_app(postgres=postgres))
    response = client.get("/api/games")
    assert response.status_code == 400
    assert response.json()["detail"] == "CHESS_USERNAME is not set"
    assert postgres.calls == []


def test_opening_lessons_can_be_empty() -> None:
    client = TestClient(create_app(postgres=EmptyLessons()))
    response = client.get("/api/lessons/openings", params={"color": "black", "player": "white"})
    assert response.status_code == 200
    assert response.json() == {"lessons": []}


def test_lesson_route_reports_postgres_down() -> None:
    client = TestClient(create_app(postgres=DownPostgres()))
    response = client.get("/api/lessons/openings", params={"color": "white", "player": "white"})
    assert response.status_code == 503
    assert response.json()["error"] == "PostgreSQL is not accepting connections."


def test_missing_graph_position_is_not_found() -> None:
    client = TestClient(create_app(postgres=FakePostgres(), neo4j=MissingGraph()))
    response = client.get("/api/positions", params={"fen": "8/8/8/8/8/8/8/K7 w - - 0 1"})
    assert response.status_code == 404
    assert "not present" in response.json()["error"]
