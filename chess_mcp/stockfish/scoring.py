"""Score normalization and legal principal-variation replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import chess
import chess.engine

from chess_mcp.stockfish.models import (
    AnalysisLine,
    EngineProvenance,
    EvaluationScore,
    PrincipalVariation,
    WDL,
)


def normalize_score(
    score: chess.engine.PovScore,
    root_player: chess.Color,
) -> EvaluationScore:
    """Normalize a score to the player at the root without flattening mates."""
    relative = score.pov(root_player)
    if relative.is_mate():
        mate = relative.mate()
        if mate is None:  # Defensive: every mate score should expose a distance.
            raise ValueError("Engine returned a mate score without a mate distance")
        return EvaluationScore(type="mate", value=mate)

    centipawns = relative.score()
    if centipawns is None:
        raise ValueError("Engine returned an unsupported score")
    return EvaluationScore(type="cp", value=centipawns)


def normalize_wdl(
    wdl: chess.engine.PovWdl | None,
    root_player: chess.Color,
) -> WDL | None:
    """Normalize engine-provided WDL permille values to the root player."""
    if wdl is None:
        return None
    relative = wdl.pov(root_player)
    return WDL(
        wins=relative.wins,
        draws=relative.draws,
        losses=relative.losses,
    )


def replay_pv(
    board: chess.Board,
    moves: Sequence[chess.Move],
) -> PrincipalVariation:
    """Replay a PV legally and return matching UCI and SAN sequences."""
    replay = board.copy(stack=False)
    uci: list[str] = []
    san: list[str] = []
    for ply, move in enumerate(moves, start=1):
        if move not in replay.legal_moves:
            raise ValueError(
                f"Engine returned an illegal PV move at ply {ply}: {move.uci()}"
            )
        uci.append(move.uci())
        san.append(replay.san(move))
        replay.push(move)
    return PrincipalVariation(uci=uci, san=san)


def analysis_line_from_info(
    board: chess.Board,
    info: Mapping[str, Any],
    *,
    engine_id: Mapping[str, str] | None = None,
    engine_options: Mapping[str, object] | None = None,
    rank: int | None = None,
) -> AnalysisLine:
    """Convert a python-chess analysis dictionary to a typed candidate line."""
    raw_score = info.get("score")
    if not isinstance(raw_score, chess.engine.PovScore):
        raise ValueError("Engine analysis did not include a score")

    raw_pv = info.get("pv", ())
    if not isinstance(raw_pv, Sequence):
        raise ValueError("Engine analysis returned an invalid principal variation")
    pv_moves = list(raw_pv)
    if not all(isinstance(move, chess.Move) for move in pv_moves):
        raise ValueError("Engine principal variation contains an invalid move")
    pv = replay_pv(board, pv_moves)

    move_uci = pv.uci[0] if pv.uci else None
    move_san = pv.san[0] if pv.san else None
    raw_wdl = info.get("wdl")
    if raw_wdl is not None and not isinstance(raw_wdl, chess.engine.PovWdl):
        raise ValueError("Engine analysis returned invalid WDL data")

    identity = engine_id or {}
    configured = engine_options or {}
    seconds = _optional_number(info.get("time"))
    return AnalysisLine(
        rank=rank or _optional_int(info.get("multipv")) or 1,
        move_uci=move_uci,
        move_san=move_san,
        score=normalize_score(raw_score, board.turn),
        wdl=normalize_wdl(raw_wdl, board.turn),
        pv=pv,
        engine=EngineProvenance(
            name=identity.get("name", "Stockfish"),
            author=identity.get("author"),
            threads=_optional_int(configured.get("Threads")),
            hash_mb=_optional_int(configured.get("Hash")),
            show_wdl=(
                bool(configured["UCI_ShowWDL"])
                if "UCI_ShowWDL" in configured
                else None
            ),
            depth=_optional_int(info.get("depth")),
            seldepth=_optional_int(info.get("seldepth")),
            nodes=_optional_int(info.get("nodes")),
            time_ms=round(seconds * 1000) if seconds is not None else None,
        ),
    )


def centipawn_loss(
    best: EvaluationScore,
    played: EvaluationScore,
) -> int | None:
    """Return CPL only when both normalized scores are centipawn scores."""
    if best.type != "cp" or played.type != "cp":
        return None
    return max(0, best.value - played.value)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None
