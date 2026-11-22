"""Pure transforms from PostgreSQL rows to the ChessGraph v2 graph.

Nothing here touches a database, so every rule is unit-tested in
``tests/test_graph_transform.py``. ``build_graph`` returns plain row dicts,
one list per write step in ``write.py``.

Conventions (see ``etl/neo4j_db/neo4j_init.md``):

- Positions use the four-field normalized FEN.
- ``eval_cp`` on a Position is from the **side to move**, as stored in
  ``game_moves.eval_cp_before``.
- PLAYED_MOVE statistics are from the **mover's** side. ``by`` says whether
  the mover was the data owner or the opponent.
- ``material_sig`` follows the Endgame Atlas notation: the White side first,
  then ``v``, then Black; each side is K followed by Q, R, B, N and P, with
  repeated letters (``KRPPvKR``).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import chess

from chess_mcp.chess import severity_for as severity
from chess_mcp.postgres.coaching_common import opening_family
from chess_mcp.postgres.recap import BANDS

SCHEMA_VERSION = 2
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"

# Stored mate scores are flattened to +/-10000, so a larger loss is a mate swing.
MATE_SWING_CP = 5_000
# The Endgame Atlas covers positions of at most this many pieces (kings included).
ENDGAME_LINK_MAX_PIECES = 6

PIECE_ORDER = "QRBNP"
SAN_PIECES = {"N": "Knight", "B": "Bishop", "R": "Rook", "Q": "Queen", "K": "King", "O": "King"}


# --------------------------------------------------------------------------- positions


@dataclass(frozen=True)
class BoardFeatures:
    turn_color: str
    piece_count: int
    material_sig: str
    majors_minors: int
    white_backrank: int
    black_backrank: int

    @property
    def phase(self) -> str:
        """Simplified Lichess "divider" rule.

        - endgame: at most 6 queens, rooks, bishops and knights in total;
        - opening: more than 10 of them, and each side still has at least 4
          pieces on its own back rank;
        - middlegame otherwise.
        """
        if self.majors_minors <= 6:
            return "endgame"
        if self.majors_minors > 10 and self.white_backrank >= 4 and self.black_backrank >= 4:
            return "opening"
        return "middlegame"


def board_features(fen_norm: str) -> BoardFeatures:
    parts = fen_norm.split()
    placement = parts[0]
    turn = parts[1] if len(parts) > 1 else "w"
    ranks = placement.split("/")
    white: Counter[str] = Counter()
    black: Counter[str] = Counter()
    for char in placement:
        if char.isalpha():
            (white if char.isupper() else black)[char.upper()] += 1

    def back_rank(rank: str, upper: bool) -> int:
        return sum(1 for char in rank if char.isalpha() and char.isupper() == upper)

    def side(counts: Counter[str]) -> str:
        return "K" + "".join(piece * counts[piece] for piece in PIECE_ORDER)

    return BoardFeatures(
        turn_color=turn,
        piece_count=sum(white.values()) + sum(black.values()),
        material_sig=f"{side(white)}v{side(black)}",
        majors_minors=sum(counts[p] for counts in (white, black) for p in "QRBN"),
        white_backrank=back_rank(ranks[7], True) if len(ranks) == 8 else 0,
        black_backrank=back_rank(ranks[0], False) if len(ranks) == 8 else 0,
    )


def move_metadata(san: str, uci: str) -> dict[str, Any]:
    san = san.strip()
    return {
        "moved_piece": SAN_PIECES.get(san[:1], "Pawn") if san else None,
        "from_square": uci[:2],
        "to_square": uci[2:4],
        "promotion": uci[4:5] or None,
        "is_capture": "x" in san,
        "is_check": san.endswith("+") or san.endswith("#"),
    }


def rating_band(elo: int | None) -> str | None:
    if elo is None:
        return None
    thresholds = (1700, 1800, 1900, 2000)
    for (band, _label), limit in zip(BANDS, thresholds, strict=False):
        if elo < limit:
            return band
    return BANDS[-1][0]


def replay_target(fen_norm: str, uci: str) -> tuple[str, str] | None:
    """Return (target fen_norm, SAN) of a legal move, or None."""
    try:
        board = chess.Board(f"{fen_norm} 0 1")
        move = chess.Move.from_uci(uci)
    except ValueError:
        return None
    if move not in board.legal_moves:
        return None
    san = board.san(move)
    board.push(move)
    return " ".join(board.fen(en_passant="legal").split()[:4]), san


def _normalize(fen: str) -> str:
    return " ".join(fen.split()[:4])


def _flip(outcome: str) -> str:
    return {"win": "loss", "loss": "win"}.get(outcome, outcome)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _round(value: float | None, digits: int | None = None) -> Any:
    if value is None:
        return None
    return round(value) if digits is None else round(value, digits)


# --------------------------------------------------------------------------- theory


@dataclass
class Theory:
    """Opening lines replayed into positions and moves."""

    edges: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    positions: set[str] = field(default_factory=set)
    line_positions: list[dict[str, Any]] = field(default_factory=list)
    epds: set[str] = field(default_factory=set)


def replay_theory(openings: Iterable[Mapping[str, Any]]) -> Theory:
    theory = Theory()
    theory.positions.add(START_FEN)
    for row in openings:
        epd = _normalize(str(row["epd_norm"]))
        theory.epds.add(epd)
        theory.positions.add(epd)
        board = chess.Board()
        for ply, token in enumerate(str(row.get("uci_line") or "").split(), start=1):
            try:
                move = chess.Move.from_uci(token)
            except ValueError:
                break
            if move not in board.legal_moves:
                break
            before = _normalize(board.fen(en_passant="legal"))
            san = board.san(move)
            board.push(move)
            after = _normalize(board.fen(en_passant="legal"))
            edge = theory.edges.setdefault(
                (before, token),
                {"fen_before": before, "fen_after": after, "uci_move": token, "san_move": san, "eco_codes": set()},
            )
            edge["eco_codes"].add(row.get("eco_code"))
            theory.positions.update((before, after))
            if after != epd:
                theory.line_positions.append({"fen_norm": after, "epd_norm": epd, "ply": ply})
    return theory


# --------------------------------------------------------------------------- graph


@dataclass
class GraphPayload:
    positions: list[dict[str, Any]]
    openings: list[dict[str, Any]]
    theory_moves: list[dict[str, Any]]
    in_opening: list[dict[str, Any]]
    endgame_patterns: list[dict[str, Any]]
    endgame_benchmarks: list[dict[str, Any]]
    endgame_links: list[dict[str, Any]]
    players: list[dict[str, Any]]
    games: list[dict[str, Any]]
    played_as: list[dict[str, Any]]
    played_moves: list[dict[str, Any]]
    reached: list[dict[str, Any]]
    opened_with: list[dict[str, Any]]
    left_theory: list[dict[str, Any]]
    entered_endgame: list[dict[str, Any]]
    mistakes: list[dict[str, Any]]
    engine_best: list[dict[str, Any]]
    meta: dict[str, Any]

    def counts(self) -> dict[str, int]:
        return {name: len(value) for name, value in vars(self).items() if isinstance(value, list)}


def build_graph(
    *,
    games: Sequence[Mapping[str, Any]],
    moves: Sequence[Mapping[str, Any]],
    openings: Sequence[Mapping[str, Any]],
    endgame_patterns: Sequence[Mapping[str, Any]],
    endgame_samples: Sequence[Mapping[str, Any]],
    owner: str,
    loaded_at: datetime | None = None,
) -> GraphPayload:
    """Turn PostgreSQL rows into graph rows. ``moves`` must be ordered by game and ply."""
    owner_key = owner.strip().casefold()
    theory = replay_theory(openings)
    games_by_id = {int(game["game_id"]): game for game in games}

    def owner_color(game: Mapping[str, Any]) -> str | None:
        color = str(game.get("user_color") or "").strip()
        return {"white": "w", "black": "b"}.get(color)

    # ---- per-position accumulators
    eval_before: dict[str, list[int]] = defaultdict(list)
    eval_after_flipped: dict[str, list[int]] = defaultdict(list)
    best_votes: dict[str, Counter[str]] = defaultdict(Counter)
    visits: dict[str, set[int]] = defaultdict(set)
    reached: list[dict[str, Any]] = []
    moves_by_game: dict[int, list[Mapping[str, Any]]] = defaultdict(list)

    # ---- per-move accumulators, keyed (fen_before, uci, by)
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}

    for row in moves:
        game_id = int(row["game_id"])
        game = games_by_id.get(game_id)
        if game is None:
            continue
        moves_by_game[game_id].append(row)
        before, after = str(row["fen_before_norm"]), str(row["fen_after_norm"])
        if row.get("eval_cp_before") is not None:
            eval_before[before].append(int(row["eval_cp_before"]))
        if row.get("eval_cp_after") is not None:
            eval_after_flipped[after].append(-int(row["eval_cp_after"]))
        if row.get("best_move_uci"):
            best_votes[before][str(row["best_move_uci"])] += 1

        mover_is_owner = row["turn_color"] == owner_color(game)
        by = "owner" if mover_is_owner else "opponent"
        outcome = str(game.get("user_outcome") or "other")
        mover_outcome = outcome if mover_is_owner else _flip(outcome)
        key = (before, str(row["uci_move"]), by)
        entry = agg.get(key)
        if entry is None:
            entry = agg[key] = {
                "fen_before": before,
                "fen_after": after,
                "uci_move": str(row["uci_move"]),
                "by": by,
                "san_move": str(row["san_move"]),
                "games": {},
                "times": 0,
                "cp_losses": [],
                "evals_after": [],
                "severity": Counter(),
            }
        entry["times"] += 1
        entry["games"].setdefault(game_id, mover_outcome)
        if row.get("cp_loss") is not None:
            entry["cp_losses"].append(int(row["cp_loss"]))
            label = severity(int(row["cp_loss"]))
            if label:
                entry["severity"][label] += 1
        if row.get("eval_cp_after") is not None:
            entry["evals_after"].append(int(row["eval_cp_after"]))

    # ---- game-level edges
    opened_with: list[dict[str, Any]] = []
    left_theory: list[dict[str, Any]] = []
    entered_endgame: list[dict[str, Any]] = []
    mistakes: list[dict[str, Any]] = []
    feature_cache: dict[str, BoardFeatures] = {}

    def features(fen: str) -> BoardFeatures:
        cached = feature_cache.get(fen)
        if cached is None:
            cached = feature_cache[fen] = board_features(fen)
        return cached

    for game_id, game_moves in moves_by_game.items():
        game = games_by_id[game_id]
        color = owner_color(game)
        start = str(game_moves[0]["fen_before_norm"])
        visits[start].add(game_id)
        reached.append({"game_id": game_id, "fen_norm": start, "ply": 0, "owner_to_move": features(start).turn_color == color})
        deepest_opening: tuple[int, str] | None = None
        left = False
        endgame_seen = features(start).phase == "endgame"
        for row in game_moves:
            ply = int(row["ply_number"])
            before, after, uci = str(row["fen_before_norm"]), str(row["fen_after_norm"]), str(row["uci_move"])
            mover_is_owner = row["turn_color"] == color
            visits[after].add(game_id)
            reached.append({"game_id": game_id, "fen_norm": after, "ply": ply, "owner_to_move": features(after).turn_color == color})
            if after in theory.epds:
                deepest_opening = (ply, after)
            if not left and (before, uci) not in theory.edges:
                left = True
                left_theory.append(
                    {
                        "game_id": game_id,
                        "fen_norm": before,
                        "ply": ply,
                        "played_uci": uci,
                        "played_san": str(row["san_move"]),
                        "by": "owner" if mover_is_owner else "opponent",
                    }
                )
            if not endgame_seen and features(after).phase == "endgame":
                endgame_seen = True
                entered_endgame.append(
                    {"game_id": game_id, "fen_norm": after, "ply": ply, "material_sig": features(after).material_sig}
                )
            label = severity(row.get("cp_loss"))
            if mover_is_owner and label:
                cp_loss = int(row["cp_loss"])
                mistakes.append(
                    {
                        "game_id": game_id,
                        "fen_norm": before,
                        "ply": ply,
                        "severity": label,
                        "cp_loss": cp_loss,
                        "mate_swing": cp_loss >= MATE_SWING_CP,
                        "played_uci": uci,
                        "played_san": str(row["san_move"]),
                        "best_uci": row.get("best_move_uci"),
                    }
                )
        if deepest_opening is not None:
            opened_with.append({"game_id": game_id, "epd_norm": deepest_opening[1], "ply": deepest_opening[0]})

    # ---- positions
    all_fens: set[str] = set(visits) | theory.positions
    all_fens.update(_normalize(str(row["fen_norm"])) for row in endgame_samples)
    for row in agg.values():
        all_fens.add(row["fen_after"])

    best_move: dict[str, str] = {fen: votes.most_common(1)[0][0] for fen, votes in best_votes.items()}
    engine_best: list[dict[str, Any]] = []
    best_san: dict[str, str] = {}
    for fen, uci in best_move.items():
        replayed = replay_target(fen, uci)
        if replayed is None:
            continue
        target, san = replayed
        best_san[fen] = san
        if target in all_fens:
            engine_best.append({"fen_before": fen, "fen_after": target, "uci": uci, "san": san})

    positions: list[dict[str, Any]] = []
    endgame_links: list[dict[str, Any]] = []
    for fen in sorted(all_fens):
        feats = features(fen)
        evals = eval_before.get(fen) or eval_after_flipped.get(fen) or []
        positions.append(
            {
                "fen_norm": fen,
                "turn_color": feats.turn_color,
                "piece_count": feats.piece_count,
                "material_sig": feats.material_sig,
                "phase": feats.phase,
                "is_theory": fen in theory.positions,
                "visit_games": len(visits.get(fen, ())),
                "eval_cp": _round(_mean(evals)),
                "eval_samples": len(evals),
                "best_move_uci": best_move.get(fen),
                "best_move_san": best_san.get(fen),
            }
        )
        if feats.piece_count <= ENDGAME_LINK_MAX_PIECES and fen in visits:
            endgame_links.append({"fen_norm": fen, "endgame_type": feats.material_sig})

    # ---- played moves
    played_moves: list[dict[str, Any]] = []
    for entry in agg.values():
        outcomes = Counter(entry["games"].values())
        n_games = len(entry["games"])
        wins, draws, losses = outcomes["win"], outcomes["draw"], outcomes["loss"]
        played_moves.append(
            {
                "fen_before": entry["fen_before"],
                "fen_after": entry["fen_after"],
                "uci_move": entry["uci_move"],
                "by": entry["by"],
                "san_move": entry["san_move"],
                **move_metadata(entry["san_move"], entry["uci_move"]),
                "games": n_games,
                "times": entry["times"],
                "wins": wins,
                "draws": draws,
                "losses": losses,
                "score_pct": _round(100 * (wins + draws / 2) / n_games, 1) if n_games else None,
                "avg_cp_loss": _round(_mean(entry["cp_losses"])),
                "avg_eval_after": _round(_mean(entry["evals_after"])),
                "inaccuracies": entry["severity"]["inaccuracy"],
                "mistakes": entry["severity"]["mistake"],
                "blunders": entry["severity"]["blunder"],
                "is_engine_best": best_move.get(entry["fen_before"]) == entry["uci_move"],
            }
        )

    theory_moves = [
        {
            **{key: value for key, value in edge.items() if key != "eco_codes"},
            **move_metadata(edge["san_move"], edge["uci_move"]),
            "eco_codes": sorted(code for code in edge["eco_codes"] if code),
        }
        for edge in theory.edges.values()
    ]

    opening_rows = [
        {
            "epd_norm": _normalize(str(row["epd_norm"])),
            "opening_id": row.get("opening_id"),
            "eco_volume": row.get("eco_volume"),
            "eco_code": row.get("eco_code"),
            "opening_name": row.get("opening_name"),
            "family": opening_family(str(row.get("opening_name") or "")) or None,
            "pgn_line": row.get("pgn_line"),
            "uci_line": row.get("uci_line"),
        }
        for row in openings
    ]

    # ---- players and games
    players: dict[str, dict[str, Any]] = {}
    played_as: list[dict[str, Any]] = []
    game_rows: list[dict[str, Any]] = []
    for game in games:
        game_id = int(game["game_id"])
        for color in ("white", "black"):
            name = str(game.get(f"{color}_username") or "").strip()
            if not name:
                continue
            # Chess.com names are case-insensitive: the first spelling seen is canonical.
            player = players.setdefault(name.casefold(), {"username": name, "is_owner": name.casefold() == owner_key})
            played_as.append(
                {"username": player["username"], "game_id": game_id, "color": color, "elo": game.get(f"{color}_elo")}
            )
        played_date = game.get("played_date")
        game_rows.append(
            {
                "game_id": game_id,
                "game_type": str(game.get("game_type")),
                "played_date": played_date,
                "user_color": game.get("user_color"),
                "user_elo": game.get("user_elo"),
                "opponent_elo": game.get("opponent_elo"),
                "rating_band": rating_band(game.get("user_elo")),
                "user_outcome": game.get("user_outcome"),
                "result": str(game.get("result")),
                "termination": game.get("termination"),
                "time_control": game.get("time_control_raw"),
                "base_time_sec": game.get("base_time_sec"),
                "increment_sec": game.get("increment_sec"),
                "eco_code": game.get("eco_code"),
                "opening_name": game.get("opening_name"),
                "total_plies": game.get("total_plies"),
            }
        )

    benchmarks = []
    for row in endgame_samples:
        benchmarks.append(
            {
                "fen_norm": _normalize(str(row["fen_norm"])),
                "endgame_type": row["endgame_type"],
                "benchmark_move_uci": row.get("human_move_uci"),
                "elo_tier": row.get("elo_tier"),
                "player_elo": row.get("player_elo"),
            }
        )

    payload = GraphPayload(
        positions=positions,
        openings=opening_rows,
        theory_moves=theory_moves,
        in_opening=theory.line_positions,
        endgame_patterns=[dict(row) for row in endgame_patterns],
        endgame_benchmarks=benchmarks,
        endgame_links=endgame_links,
        players=list(players.values()),
        games=game_rows,
        played_as=played_as,
        played_moves=played_moves,
        reached=reached,
        opened_with=opened_with,
        left_theory=left_theory,
        entered_endgame=entered_endgame,
        mistakes=mistakes,
        engine_best=engine_best,
        meta={},
    )
    payload.meta = {
        "schema_version": SCHEMA_VERSION,
        "loaded_at": (loaded_at or datetime.now(UTC)).isoformat(timespec="seconds"),
        "counts": payload.counts(),
    }
    return payload
