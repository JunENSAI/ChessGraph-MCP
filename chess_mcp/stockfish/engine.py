"""Lazy, serialized access to one persistent python-chess Stockfish process."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Protocol, cast

import chess
import chess.engine

from chess_mcp.chess import parse_board
from chess_mcp.config import StockfishSettings, get_stockfish_settings
from chess_mcp.stockfish.models import (
    AnalysisLine,
    LimitType,
    MoveComparison,
    PositionAnalysis,
    SearchLimit,
    ValidatedLine,
    ValidatedMove,
)
from chess_mcp.stockfish.scoring import (
    analysis_line_from_info,
    centipawn_loss,
)


class EngineLike(Protocol):
    """The SimpleEngine surface used by this package."""

    id: Mapping[str, str]
    options: Mapping[str, object]

    def configure(self, options: Mapping[str, object]) -> None: ...

    def analyse(
        self,
        board: chess.Board,
        limit: chess.engine.Limit,
        *,
        multipv: int | None = None,
        info: chess.engine.Info = chess.engine.INFO_ALL,
        root_moves: list[chess.Move] | None = None,
    ) -> chess.engine.InfoDict | list[chess.engine.InfoDict]: ...

    def quit(self) -> None: ...


EngineFactory = Callable[[str], EngineLike]
SettingsGetter = Callable[[], StockfishSettings]


class StockfishEngine:
    """Own one lazily-created engine and serialize every interaction with it."""

    def __init__(
        self,
        *,
        settings_getter: SettingsGetter = get_stockfish_settings,
        engine_factory: EngineFactory | None = None,
    ) -> None:
        self._settings_getter = settings_getter
        self._engine_factory = engine_factory or _launch_engine
        self._engine: EngineLike | None = None
        self._configured_options: dict[str, object] = {}
        self._lock = threading.Lock()

    @property
    def started(self) -> bool:
        """Whether the child process has been launched."""
        with self._lock:
            return self._engine is not None

    def analyse(
        self,
        board: chess.Board,
        limit: chess.engine.Limit,
        *,
        multipv: int,
    ) -> tuple[
        list[chess.engine.InfoDict],
        dict[str, str],
        dict[str, object],
    ]:
        """Run a MultiPV search while holding the process-wide engine lock."""
        with self._lock:
            engine = self._ensure_engine_locked()
            result = engine.analyse(
                board,
                limit,
                multipv=multipv,
                info=chess.engine.INFO_ALL,
            )
            infos = result if isinstance(result, list) else [result]
            return infos, dict(engine.id), dict(self._configured_options)

    def compare(
        self,
        board: chess.Board,
        played_move: chess.Move,
        limit: chess.engine.Limit,
    ) -> tuple[
        chess.engine.InfoDict,
        chess.engine.InfoDict,
        dict[str, str],
        dict[str, object],
    ]:
        """Run unrestricted and played-move searches atomically at one budget."""
        with self._lock:
            engine = self._ensure_engine_locked()
            best = engine.analyse(
                board,
                limit,
                info=chess.engine.INFO_ALL,
            )
            played = engine.analyse(
                board,
                limit,
                info=chess.engine.INFO_ALL,
                root_moves=[played_move],
            )
            if isinstance(best, list) or isinstance(played, list):
                raise ValueError("Engine returned unexpected MultiPV comparison data")
            return (
                best,
                played,
                dict(engine.id),
                dict(self._configured_options),
            )

    def close(self) -> None:
        """Quit the child process once, if it was started."""
        with self._lock:
            engine, self._engine = self._engine, None
            if engine is not None:
                engine.quit()

    def _ensure_engine_locked(self) -> EngineLike:
        if self._engine is not None:
            return self._engine

        settings = self._settings_getter()
        engine = self._engine_factory(str(settings.path))
        try:
            configuration: dict[str, object] = {}
            options = getattr(engine, "options", {})
            if "Threads" in options:
                configuration["Threads"] = settings.threads
            if "Hash" in options:
                configuration["Hash"] = settings.hash_mb
            if "UCI_ShowWDL" in options:
                configuration["UCI_ShowWDL"] = True
            if configuration:
                engine.configure(configuration)
        except Exception:
            engine.quit()
            raise
        self._configured_options = configuration
        self._engine = engine
        return engine


class StockfishService:
    """Validate tool inputs and map raw engine data to response models."""

    def __init__(
        self,
        engine: StockfishEngine | None = None,
        *,
        settings_getter: SettingsGetter = get_stockfish_settings,
    ) -> None:
        self._settings_getter = settings_getter
        self.engine = engine or StockfishEngine(settings_getter=settings_getter)

    def analyze_position(
        self,
        fen: str,
        *,
        limit_type: LimitType = "depth",
        limit_value: int | None = None,
        multipv: int = 1,
    ) -> PositionAnalysis:
        board = parse_board(fen)
        settings = self._settings_getter()
        engine_limit, response_limit = build_limit(
            settings,
            limit_type,
            limit_value,
        )
        bounded_multipv = _bounded_integer(
            "multipv",
            multipv,
            maximum=settings.max_multipv,
        )

        infos, engine_id, engine_options = self.engine.analyse(
            board,
            engine_limit,
            multipv=bounded_multipv,
        )
        lines = [
            analysis_line_from_info(
                board,
                info,
                engine_id=engine_id,
                engine_options=engine_options,
                rank=index,
            )
            for index, info in enumerate(infos, start=1)
        ]
        return PositionAnalysis(
            fen=board.fen(en_passant="fen"),
            root_player=_color_name(board.turn),
            limit=response_limit,
            multipv=bounded_multipv,
            lines=lines,
        )

    def compare_move(
        self,
        fen: str,
        played_move_uci: str,
        *,
        limit_type: LimitType = "depth",
        limit_value: int | None = None,
    ) -> MoveComparison:
        board = parse_board(fen)
        move = _legal_uci_move(board, played_move_uci)
        settings = self._settings_getter()
        engine_limit, response_limit = build_limit(
            settings,
            limit_type,
            limit_value,
        )

        best_info, played_info, engine_id, engine_options = self.engine.compare(
            board,
            move,
            engine_limit,
        )
        best = analysis_line_from_info(
            board,
            best_info,
            engine_id=engine_id,
            engine_options=engine_options,
            rank=1,
        )
        played = analysis_line_from_info(
            board,
            played_info,
            engine_id=engine_id,
            engine_options=engine_options,
            rank=1,
        )
        return MoveComparison(
            fen=board.fen(en_passant="fen"),
            root_player=_color_name(board.turn),
            played_move_uci=move.uci(),
            played_move_san=board.san(move),
            limit=response_limit,
            best=best,
            played=played,
            centipawn_loss=centipawn_loss(best.score, played.score),
        )

    def validate_line(self, fen: str, moves_uci: list[str]) -> ValidatedLine:
        board = parse_board(fen)
        initial_fen = board.fen(en_passant="fen")
        moves: list[ValidatedMove] = []
        for ply, token in enumerate(moves_uci, start=1):
            try:
                move = _legal_uci_move(board, token)
            except ValueError as exc:
                raise ValueError(f"Invalid line at ply {ply}: {exc}") from exc
            san = board.san(move)
            board.push(move)
            moves.append(
                ValidatedMove(
                    ply=ply,
                    uci=move.uci(),
                    san=san,
                    fen_after=board.fen(en_passant="fen"),
                )
            )
        return ValidatedLine(
            initial_fen=initial_fen,
            moves=moves,
            final_fen=board.fen(en_passant="fen"),
        )

    def close(self) -> None:
        self.engine.close()


def build_limit(
    settings: StockfishSettings,
    limit_type: LimitType,
    limit_value: int | None,
) -> tuple[chess.engine.Limit, SearchLimit]:
    """Build a python-chess limit after enforcing configured hard bounds."""
    if limit_type == "depth":
        requested = settings.default_depth if limit_value is None else limit_value
        value = _bounded_integer("depth", requested, maximum=settings.max_depth)
        return (
            chess.engine.Limit(depth=value),
            SearchLimit(type="depth", value=value, unit="plies"),
        )
    if limit_type == "nodes":
        if limit_value is None:
            raise ValueError("limit_value is required when limit_type is 'nodes'")
        value = _bounded_integer(
            "nodes",
            limit_value,
            maximum=settings.max_nodes,
        )
        return (
            chess.engine.Limit(nodes=value),
            SearchLimit(type="nodes", value=value, unit="nodes"),
        )
    if limit_type == "time":
        if limit_value is None:
            raise ValueError("limit_value is required when limit_type is 'time'")
        value = _bounded_integer(
            "time in milliseconds",
            limit_value,
            maximum=settings.max_time_ms,
        )
        return (
            chess.engine.Limit(time=value / 1000),
            SearchLimit(type="time", value=value, unit="milliseconds"),
        )
    raise ValueError("limit_type must be one of: depth, nodes, time")


def _launch_engine(command: str) -> EngineLike:
    return cast(EngineLike, chess.engine.SimpleEngine.popen_uci(command))


def _legal_uci_move(board: chess.Board, token: str) -> chess.Move:
    try:
        move = chess.Move.from_uci(token.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid UCI move: {token!r}") from exc
    if move not in board.legal_moves:
        raise ValueError(f"Illegal move for the position: {move.uci()}")
    return move


def _bounded_integer(name: str, value: int, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return min(value, maximum)


def _color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"
