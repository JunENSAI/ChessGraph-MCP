"""HTTP retrieval API for the coach UI.

Hermes keeps the MCP servers. This process calls the same repositories for
the facts the interface renders before a question is asked: games, opening
rows, graph context, and a bounded Stockfish search. It does not explain.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from chess_mcp.config import get_chess_username, get_neo4j_settings, get_postgres_settings
from chess_mcp.neo4j.repository import Neo4jRepository
from chess_mcp.postgres.models import GameType, UserOutcome
from chess_mcp.postgres.repository import PostgresRepository
from chess_mcp.stockfish.engine import StockfishService
from chess_mcp.stockfish.models import LimitType


class AnalyzeRequest(BaseModel):
    fen: str
    limit_type: LimitType = "depth"
    limit_value: int | None = Field(default=None, ge=1)
    multipv: int = Field(default=1, ge=1)


class CompareRequest(BaseModel):
    fen: str
    played_move_uci: str
    limit_type: LimitType = "depth"
    limit_value: int | None = Field(default=None, ge=1)


class ValidateRequest(BaseModel):
    fen: str
    moves_uci: list[str]


def create_app(
    *,
    postgres: PostgresRepository | None = None,
    neo4j: Neo4jRepository | None = None,
    stockfish: StockfishService | None = None,
) -> FastAPI:
    """Build the API. Injected repositories are for tests and are not closed here."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.postgres is None:
            app.state.postgres = PostgresRepository.from_settings(get_postgres_settings())
            app.state.owns_postgres = True
        try:
            yield
        finally:
            if app.state.owns_postgres:
                app.state.postgres.close()
            if app.state.owns_neo4j and app.state.neo4j is not None:
                app.state.neo4j.close()
            if app.state.owns_stockfish and app.state.stockfish is not None:
                app.state.stockfish.close()

    app = FastAPI(title="ChessGraph retrieval", lifespan=lifespan)
    app.state.postgres = postgres
    app.state.neo4j = neo4j
    app.state.stockfish = stockfish
    app.state.owns_postgres = False
    app.state.owns_neo4j = False
    app.state.owns_stockfish = False

    def postgres_repo(request: Request) -> PostgresRepository:
        return request.app.state.postgres

    def configured_player(player: str | None) -> str:
        selected = (player if player is not None else get_chess_username()).strip()
        if not selected:
            raise HTTPException(status_code=400, detail="CHESS_USERNAME is not set")
        return selected

    def neo4j_repo(request: Request) -> Neo4jRepository:
        if request.app.state.neo4j is None:
            request.app.state.neo4j = Neo4jRepository.from_settings(get_neo4j_settings())
            request.app.state.owns_neo4j = True
        return request.app.state.neo4j

    def stockfish_service(request: Request) -> StockfishService:
        if request.app.state.stockfish is None:
            request.app.state.stockfish = StockfishService()
            request.app.state.owns_stockfish = True
        return request.app.state.stockfish

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/recap")
    def recap(repo: PostgresRepository = Depends(postgres_repo)):
        return repo.get_rating_recap()

    @app.get("/api/games")
    def games(
        player: str | None = None,
        game_type: GameType | None = None,
        user_outcome: UserOutcome | None = None,
        eco_code: str | None = None,
        played_from: date | None = None,
        played_to: date | None = None,
        limit: int = Query(default=20, ge=1),
        offset: int = Query(default=0, ge=0),
        repo: PostgresRepository = Depends(postgres_repo),
    ):
        return {
            "games": repo.list_games(
                player=configured_player(player),
                game_type=game_type,
                user_outcome=user_outcome,
                eco_code=eco_code,
                played_from=played_from,
                played_to=played_to,
                limit=limit,
                offset=offset,
            )
        }

    @app.get("/api/games/{game_id}")
    def game(game_id: int, repo: PostgresRepository = Depends(postgres_repo)):
        detail = repo.get_game(game_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Game not found")
        return detail

    @app.get("/api/games/{game_id}/moves")
    def game_moves(
        game_id: int,
        start_ply: int = Query(default=1, ge=1),
        limit: int = Query(default=100, ge=1),
        repo: PostgresRepository = Depends(postgres_repo),
    ):
        return {
            "game_id": game_id,
            "start_ply": start_ply,
            "moves": repo.get_game_moves(game_id, start_ply=start_ply, limit=limit),
        }

    @app.get("/api/lessons/openings")
    def lesson_openings(
        color: Literal["white", "black"],
        player: str | None = None,
        limit: int = Query(default=5, ge=1, le=40),
        repo: PostgresRepository = Depends(postgres_repo),
    ):
        return {
            "lessons": repo.list_opening_lessons(
                player=configured_player(player),
                color=color,
                limit=limit,
            )
        }

    @app.get("/api/lessons/endgames")
    def lesson_endgames(
        player: str | None = None,
        limit: int = Query(default=5, ge=1, le=5),
        repo: PostgresRepository = Depends(postgres_repo),
    ):
        selected = configured_player(player)
        summary = repo.get_player_summary(selected)
        tier, lessons = repo.list_endgame_lessons(
            average_rating=summary.average_rating,
            limit=limit,
        )
        return {"elo_tier": tier, "lessons": lessons}

    @app.get("/api/coach/brief")
    def coaching_brief(
        player: str | None = None,
        repo: PostgresRepository = Depends(postgres_repo),
    ):
        selected = configured_player(player)
        return repo.get_coaching_brief(selected)

    @app.get("/api/player")
    def player(
        username: str | None = None,
        game_type: GameType | None = None,
        repo: PostgresRepository = Depends(postgres_repo),
    ):
        selected = (username or get_chess_username()).strip()
        if not selected:
            raise HTTPException(status_code=400, detail="CHESS_USERNAME is not set")
        return repo.get_player_summary(selected, game_type=game_type)

    @app.get("/api/openings")
    def openings(
        fen: str,
        limit: int = Query(default=20, ge=1),
        repo: PostgresRepository = Depends(postgres_repo),
    ):
        normalized_fen, rows = repo.lookup_opening(fen, limit=limit)
        return {"normalized_fen": normalized_fen, "openings": rows}

    @app.get("/api/positions")
    def position(
        fen: str,
        limit: int = Query(default=20, ge=1),
        graph: Neo4jRepository = Depends(neo4j_repo),
    ):
        return {
            "context": graph.get_position_context(fen),
            "moves": graph.get_position_moves(fen, limit=limit),
        }

    @app.post("/api/engine/analyze")
    def analyze(body: AnalyzeRequest, engine: StockfishService = Depends(stockfish_service)):
        return engine.analyze_position(
            body.fen,
            limit_type=body.limit_type,
            limit_value=body.limit_value,
            multipv=body.multipv,
        )

    @app.post("/api/engine/compare")
    def compare(body: CompareRequest, engine: StockfishService = Depends(stockfish_service)):
        return engine.compare_move(
            body.fen,
            body.played_move_uci,
            limit_type=body.limit_type,
            limit_value=body.limit_value,
        )

    @app.post("/api/engine/validate")
    def validate(body: ValidateRequest, engine: StockfishService = Depends(stockfish_service)):
        return engine.validate_line(body.fen, body.moves_uci)

    @app.exception_handler(LookupError)
    async def missing_position(_request: Request, exc: LookupError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"error": str(exc)})

    @app.exception_handler(ValueError)
    async def bad_request(_request: Request, exc: ValueError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(SQLAlchemyError)
    async def postgres_down(_request: Request, _exc: SQLAlchemyError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"error": "PostgreSQL is not accepting connections."},
        )

    @app.exception_handler(Neo4jError)
    async def neo4j_down(_request: Request, _exc: Neo4jError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"error": "Neo4j is not accepting connections."},
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
