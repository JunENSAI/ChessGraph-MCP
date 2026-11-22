"""Graph v2 transforms (etl/neo4j_db/transform.py) on a small synthetic dataset."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import chess
import pytest

from chess_mcp.chess import SEVERITY_MIN_CP, severity_for
from etl.neo4j_db.transform import (
    START_FEN,
    board_features,
    build_graph,
    rating_band,
    replay_target,
)

OWNER = "OwnerName"
LOADED_AT = datetime(2026, 11, 22, tzinfo=UTC)


def key(board: chess.Board) -> str:
    return " ".join(board.fen().split()[:4])


def epd_after(uci_line: str) -> str:
    board = chess.Board()
    for token in uci_line.split():
        board.push_uci(token)
    return key(board)


def move_rows(game_id: int, line: str, start: str | None = None, **per_ply: dict[int, Any]) -> list[dict[str, Any]]:
    """Rows shaped like game_moves. per_ply maps a column to {ply: value}."""
    board = chess.Board(f"{start} 0 1") if start else chess.Board()
    rows = []
    for ply, token in enumerate(line.split(), start=1):
        move = chess.Move.from_uci(token)
        before = key(board)
        turn = "w" if board.turn == chess.WHITE else "b"
        san = board.san(move)
        board.push(move)
        row = {
            "game_id": game_id,
            "ply_number": ply,
            "turn_color": turn,
            "san_move": san,
            "uci_move": token,
            "fen_before_norm": before,
            "fen_after_norm": key(board),
            "eval_cp_before": None,
            "eval_cp_after": None,
            "cp_loss": None,
            "best_move_uci": None,
        }
        for column, values in per_ply.items():
            if ply in values:
                row[column] = values[ply]
        rows.append(row)
    return rows


def game(game_id: int, user_color: str, outcome: str, white: str, black: str, **extra: Any) -> dict[str, Any]:
    return {
        "game_id": game_id,
        "game_type": "blitz",
        "played_date": date(2025, 1, game_id),
        "white_username": white,
        "black_username": black,
        "white_elo": 1800,
        "black_elo": 1750,
        "user_color": user_color,
        "user_elo": 1800 if user_color == "white" else 1750,
        "opponent_elo": 1750 if user_color == "white" else 1800,
        "user_outcome": outcome,
        "result": "1-0",
        "termination": "won by resignation",
        "time_control_raw": "180+2",
        "base_time_sec": 180,
        "increment_sec": 2,
        "eco_code": "C50",
        "opening_name": "Italian Game",
        "total_plies": 0,
        **extra,
    }


ITALIAN = "e2e4 e7e5 g1f3 b8c6 f1c4"
OPENINGS = [
    {"opening_id": 1, "eco_volume": "C", "eco_code": "C20", "opening_name": "King's Pawn Game", "pgn_line": "1. e4", "uci_line": "e2e4", "epd_norm": epd_after("e2e4")},
    {"opening_id": 2, "eco_volume": "C", "eco_code": "C50", "opening_name": "Italian Game", "pgn_line": "1. e4 e5 2. Nf3 Nc6 3. Bc4", "uci_line": ITALIAN, "epd_norm": epd_after(ITALIAN)},
    {"opening_id": 3, "eco_volume": "C", "eco_code": "C50", "opening_name": "Italian Game: Giuoco Piano", "pgn_line": "", "uci_line": ITALIAN + " f8c5", "epd_norm": epd_after(ITALIAN + " f8c5")},
]

# Game 1: the owner is White and wins; the opponent leaves book with 3...Nd4.
GAME_1 = move_rows(
    1,
    ITALIAN + " c6d4 f3e5",
    eval_cp_before={1: 30, 2: -25, 6: -40},
    eval_cp_after={1: 25, 6: -350, 7: 380},
    cp_loss={1: 5, 6: 310, 7: 60},
    best_move_uci={1: "e2e4", 6: "f8c5"},
)
# Game 2: the owner is Black (differently capitalised) and loses; the owner leaves book with 2...d6.
GAME_2 = move_rows(2, "e2e4 e7e5 g1f3 d7d6", cp_loss={2: 0, 4: 120}, best_move_uci={1: "e2e4"})
# Game 3 starts from a 7-minor/major position: 1.Rxa8 reaches the endgame phase.
ENDGAME_START = "r3k3/8/8/8/8/2n1b3/1N1B4/R2QK3 w - -"
GAME_3 = move_rows(3, "a1a8 e8e7", start=ENDGAME_START, cp_loss={1: 9_999})

GAMES = [
    game(1, "white", "win", OWNER, "rival"),
    game(2, "black", "loss", "rival", OWNER.upper()),
    game(3, "white", "draw", OWNER, "third"),
]
ENDGAME_SAMPLES = [
    {"fen_norm": "8/8/8/8/8/8/4K3/R3k3 b - -", "endgame_type": "KRvK", "human_move_uci": "e1d1", "elo_tier": "2000+", "player_elo": 2100},
]


@pytest.fixture(scope="module")
def payload():
    return build_graph(
        games=GAMES,
        moves=GAME_1 + GAME_2 + GAME_3,
        openings=OPENINGS,
        endgame_patterns=[{"endgame_type": "KRvK", "piece_count": 3, "benchmark_positions": 1}],
        endgame_samples=ENDGAME_SAMPLES,
        owner=OWNER,
        loaded_at=LOADED_AT,
    )


def by_key(rows: list[dict[str, Any]], *fields: str) -> dict[tuple[Any, ...], dict[str, Any]]:
    return {tuple(row[f] for f in fields): row for row in rows}


# --------------------------------------------------------------------------- pure rules


@pytest.mark.parametrize(
    ("fen", "signature"),
    [
        ("4k3/8/8/8/8/8/4P3/R3K3 w - -", "KRPvK"),
        ("4k3/q7/8/8/8/8/8/4K3 w - -", "KvKQ"),
        # Same order as Endgame Atlas types in PostgreSQL, e.g. KQBvKRN.
        ("4k3/3rn3/8/8/8/8/8/2QBK3 w - -", "KQBvKRN"),
        ("4k3/pp6/8/8/8/8/8/4K3 b - -", "KvKPP"),
    ],
)
def test_material_signature_is_white_first_in_atlas_order(fen: str, signature: str) -> None:
    assert board_features(fen).material_sig == signature


def test_phase_follows_the_simplified_lichess_divider() -> None:
    assert board_features(START_FEN).phase == "opening"
    # 14 majors and minors, but White's back rank is down to the king and a rook.
    developed = "r1bqkb1r/pppppppp/2n2n2/8/2BNPB2/2N5/PPP2PPP/R2QK3 w Qkq -"
    assert board_features(developed).majors_minors > 10
    assert board_features(developed).phase == "middlegame"
    assert board_features(ENDGAME_START).majors_minors == 7
    assert board_features(ENDGAME_START).phase == "middlegame"
    assert board_features("4k3/8/8/8/8/8/4P3/R3K3 w - -").phase == "endgame"


@pytest.mark.parametrize(
    ("loss", "label"),
    [(None, None), (49, None), (50, "inaccuracy"), (99, "inaccuracy"), (100, "mistake"), (299, "mistake"), (300, "blunder")],
)
def test_severity_thresholds(loss: int | None, label: str | None) -> None:
    assert severity_for(loss) == label
    assert SEVERITY_MIN_CP == {"inaccuracy": 50, "mistake": 100, "blunder": 300}


@pytest.mark.parametrize(
    ("elo", "band"),
    [(None, None), (1450, "under-1700"), (1700, "1700-1799"), (1999, "1900-1999"), (2000, "2000-plus")],
)
def test_rating_band_matches_the_recap_bands(elo: int | None, band: str | None) -> None:
    assert rating_band(elo) == band


def test_replay_target_returns_the_key_and_san_or_none() -> None:
    assert replay_target(START_FEN, "g1f3") == (epd_after("g1f3"), "Nf3")
    assert replay_target(START_FEN, "e2e5") is None
    assert replay_target(START_FEN, "zz") is None


# --------------------------------------------------------------------------- build_graph


def test_every_game_reaches_its_start_and_every_move(payload) -> None:
    assert len(payload.reached) == len(GAME_1) + len(GAME_2) + len(GAME_3) + len(GAMES)
    starts = [row for row in payload.reached if row["ply"] == 0]
    assert {row["game_id"]: row["fen_norm"] for row in starts} == {1: START_FEN, 2: START_FEN, 3: ENDGAME_START}
    # Owner is White in game 1: White to move at ply 0.
    assert by_key(payload.reached, "game_id", "ply")[(1, 0)]["owner_to_move"] is True
    assert by_key(payload.reached, "game_id", "ply")[(2, 0)]["owner_to_move"] is False


def test_played_moves_are_split_by_mover_and_scored_from_the_mover(payload) -> None:
    moves = by_key(payload.played_moves, "fen_before", "uci_move", "by")
    owner_e4 = moves[(START_FEN, "e2e4", "owner")]
    opponent_e4 = moves[(START_FEN, "e2e4", "opponent")]
    # Game 1: owner played 1.e4 and won. Game 2: the opponent played 1.e4 and won.
    assert (owner_e4["games"], owner_e4["wins"], owner_e4["losses"], owner_e4["score_pct"]) == (1, 1, 0, 100.0)
    assert (opponent_e4["games"], opponent_e4["wins"], opponent_e4["losses"]) == (1, 1, 0)
    assert owner_e4["is_engine_best"] is True
    nd4 = moves[(epd_after(ITALIAN), "c6d4", "opponent")]
    assert nd4["blunders"] == 1 and nd4["avg_cp_loss"] == 310
    assert nd4["avg_eval_after"] == -350


def test_position_eval_is_from_the_side_to_move(payload) -> None:
    positions = by_key(payload.positions, "fen_norm")
    start = positions[(START_FEN,)]
    assert (start["eval_cp"], start["eval_samples"]) == (30, 1)
    assert positions[(epd_after("e2e4"),)]["eval_cp"] == -25
    # Only reached as fen_after (ply 7, White moved): Black to move, eval is -eval_cp_after.
    final = positions[(GAME_1[-1]["fen_after_norm"],)]
    assert final["turn_color"] == "b" and final["eval_cp"] == -380
    assert start["visit_games"] == 2
    assert start["best_move_uci"] == "e2e4" and start["best_move_san"] == "e4"


def test_theory_moves_collect_every_eco_code(payload) -> None:
    theory = by_key(payload.theory_moves, "fen_before", "uci_move")
    assert theory[(START_FEN, "e2e4")]["eco_codes"] == ["C20", "C50"]
    assert theory[(START_FEN, "e2e4")]["san_move"] == "e4"
    positions = by_key(payload.positions, "fen_norm")
    assert positions[(epd_after(ITALIAN),)]["is_theory"] is True
    assert positions[(GAME_1[-1]["fen_after_norm"],)]["is_theory"] is False


def test_game_milestones(payload) -> None:
    opened = by_key(payload.opened_with, "game_id")
    assert opened[(1,)]["epd_norm"] == epd_after(ITALIAN) and opened[(1,)]["ply"] == 5
    assert opened[(2,)]["epd_norm"] == epd_after("e2e4")
    left = by_key(payload.left_theory, "game_id")
    assert (left[(1,)]["ply"], left[(1,)]["by"], left[(1,)]["played_san"]) == (6, "opponent", "Nd4")
    assert (left[(2,)]["ply"], left[(2,)]["by"]) == (4, "owner")
    entered = by_key(payload.entered_endgame, "game_id")
    assert set(entered) == {(3,)}
    assert entered[(3,)]["ply"] == 1


def test_mistakes_are_the_owner_moves_only(payload) -> None:
    mistakes = by_key(payload.mistakes, "game_id", "ply")
    # Game 1 ply 6 (310 cp) was the opponent's move, ply 7 (60 cp) the owner's.
    assert set(mistakes) == {(1, 7), (2, 4), (3, 1)}
    assert mistakes[(1, 7)]["severity"] == "inaccuracy"
    assert mistakes[(2, 4)]["severity"] == "mistake"
    assert mistakes[(3, 1)]["severity"] == "blunder" and mistakes[(3, 1)]["mate_swing"] is True


def test_engine_best_edges_point_at_known_positions(payload) -> None:
    edges = by_key(payload.engine_best, "fen_before")
    assert edges[(START_FEN,)]["fen_after"] == epd_after("e2e4")
    # 3...Bc5 from the Italian reaches the Giuoco Piano EPD, a theory position.
    assert edges[(epd_after(ITALIAN),)]["san"] == "Bc5"


def test_players_are_canonical_and_the_owner_is_flagged(payload) -> None:
    players = by_key(payload.players, "username")
    assert players[(OWNER,)]["is_owner"] is True
    assert players[("rival",)]["is_owner"] is False
    assert len(payload.players) == 3
    # Game 2 spells the owner in capitals; the edge still points at the canonical node.
    assert {row["username"] for row in payload.played_as if row["game_id"] == 2} == {"rival", OWNER}


def test_games_carry_v2_properties(payload) -> None:
    game_1 = by_key(payload.games, "game_id")[(1,)]
    assert game_1["played_date"] == date(2025, 1, 1)
    assert (game_1["time_control"], game_1["base_time_sec"], game_1["increment_sec"]) == ("180+2", 180, 2)
    assert game_1["rating_band"] == "1800-1899"
    assert "white_username" not in game_1


def test_openings_get_their_family_and_lines_their_positions(payload) -> None:
    families = {row["opening_name"]: row["family"] for row in payload.openings}
    assert families["Italian Game: Giuoco Piano"] == "Italian Game"
    in_opening = {(row["fen_norm"], row["epd_norm"]) for row in payload.in_opening}
    assert (epd_after("e2e4"), epd_after(ITALIAN)) in in_opening
    assert (epd_after(ITALIAN), epd_after(ITALIAN)) not in in_opening


def test_endgame_links_use_the_atlas_signature(payload) -> None:
    links = {row["endgame_type"] for row in payload.endgame_links}
    # After 1.Rxa8 in game 3: White K Q B N R, Black K B N = 8 pieces, so no link;
    # the Atlas sample position itself is linked as a benchmark instead.
    assert all(board_features(row["fen_norm"]).piece_count <= 6 for row in payload.endgame_links)
    assert links <= {row["material_sig"] for row in payload.positions}
    benchmark = payload.endgame_benchmarks[0]
    assert benchmark["endgame_type"] == "KRvK" == board_features(benchmark["fen_norm"]).material_sig


def test_meta_and_reruns_are_deterministic(payload) -> None:
    assert payload.meta["schema_version"] == 2
    assert payload.meta["loaded_at"] == "2026-11-22T00:00:00+00:00"
    assert payload.meta["counts"]["reached"] == len(payload.reached)
    again = build_graph(
        games=GAMES,
        moves=GAME_1 + GAME_2 + GAME_3,
        openings=OPENINGS,
        endgame_patterns=[{"endgame_type": "KRvK", "piece_count": 3, "benchmark_positions": 1}],
        endgame_samples=ENDGAME_SAMPLES,
        owner=OWNER,
        loaded_at=LOADED_AT,
    )
    assert again == payload
