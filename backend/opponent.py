"""Stockfish as a playing opponent at a chosen strength.

The analysis engine (`chess_mcp.stockfish`) always searches at full strength,
so the opponent runs in its own Stockfish process. Strength uses Stockfish's
``UCI_LimitStrength`` / ``UCI_Elo`` options; ``elo=None`` plays at full strength.
Only the UI's play mode calls this; no MCP tool exposes it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import chess
import chess.engine
from pydantic import BaseModel

from chess_mcp.chess import parse_board
from chess_mcp.config import get_stockfish_settings

# Stockfish 17.x accepts UCI_Elo in this range; the UI levels stay inside it.
MIN_ELO = 1320
MAX_ELO = 3190
MIN_MOVETIME_MS = 50
MAX_MOVETIME_MS = 3000


class PlayedMove(BaseModel):
    uci: str
    san: str
    fen: str
    elo: int | None
    score_type: str | None = None
    score_value: int | None = None
    """Score of the searched position from the side that moved, before the move."""


EngineFactory = Callable[[str], Any]


def _launch(command: str) -> Any:
    return chess.engine.SimpleEngine.popen_uci(command)


class Opponent:
    """One lazily started Stockfish process; one move at a time."""

    def __init__(self, engine_factory: EngineFactory | None = None) -> None:
        self._factory = engine_factory or _launch
        self._engine: Any = None
        self._lock = threading.Lock()

    def play(self, fen: str, elo: int | None, movetime_ms: int) -> PlayedMove:
        board = parse_board(fen)
        if board.is_game_over(claim_draw=True):
            raise ValueError("The game is over in this position.")
        if elo is not None and not MIN_ELO <= elo <= MAX_ELO:
            raise ValueError(f"elo must be between {MIN_ELO} and {MAX_ELO}, or null for full strength")
        if not MIN_MOVETIME_MS <= movetime_ms <= MAX_MOVETIME_MS:
            raise ValueError(f"movetime_ms must be between {MIN_MOVETIME_MS} and {MAX_MOVETIME_MS}")
        options: dict[str, object] = (
            {"UCI_LimitStrength": True, "UCI_Elo": elo} if elo is not None else {"UCI_LimitStrength": False}
        )
        with self._lock:
            if self._engine is None:
                self._engine = self._factory(str(get_stockfish_settings().path))
            result = self._engine.play(
                board,
                chess.engine.Limit(time=movetime_ms / 1000),
                info=chess.engine.INFO_SCORE,
                options=options,
            )
        if result.move is None or result.move not in board.legal_moves:
            raise ValueError("Stockfish returned no legal move.")
        san = board.san(result.move)
        score = result.info.get("score") if result.info else None
        score_type: str | None = None
        score_value: int | None = None
        if score is not None:
            pov = score.pov(board.turn)
            if pov.is_mate():
                score_type, score_value = "mate", pov.mate()
            else:
                score_type, score_value = "cp", pov.score()
        board.push(result.move)
        return PlayedMove(
            uci=result.move.uci(),
            san=san,
            fen=board.fen(),
            elo=elo,
            score_type=score_type,
            score_value=score_value,
        )

    def close(self) -> None:
        with self._lock:
            engine, self._engine = self._engine, None
        if engine is not None:
            engine.quit()
