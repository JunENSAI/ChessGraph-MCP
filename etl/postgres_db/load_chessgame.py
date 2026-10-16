import sys
import hashlib
import logging
import re
from pathlib import Path

import chess
import chess.pgn
from sqlalchemy import text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_opening import normalize_fen

logger = logging.getLogger(__name__)

INSERT_GAME_SQL = text(
    """
    INSERT INTO games (
        game_hash, game_type, event, site, played_date, end_time_utc, round,
        white_username, black_username, white_elo, black_elo,
        user_color, user_elo, opponent_elo, user_outcome,
        result, time_control_raw, base_time_sec, increment_sec, termination,
        eco_code, opening_name, total_plies, pgn_moves_raw
    ) VALUES (
        :game_hash, :game_type, :event, :site, :played_date, :end_time_utc, :round,
        :white_username, :black_username, :white_elo, :black_elo,
        :user_color, :user_elo, :opponent_elo, :user_outcome,
        :result, :time_control_raw, :base_time_sec, :increment_sec, :termination,
        :eco_code, :opening_name, :total_plies, :pgn_moves_raw
    )
    ON CONFLICT (game_hash) DO NOTHING
    RETURNING game_id;
    """
)

INSERT_MOVES_SQL = text(
    """
    INSERT INTO game_moves (
        game_id, ply_number, move_number, turn_color,
        san_move, uci_move, fen_before_norm, fen_after_norm, clock_rem_sec
    ) VALUES (
        :game_id, :ply_number, :move_number, :turn_color,
        :san_move, :uci_move, :fen_before_norm, :fen_after_norm, :clock_rem_sec
    )
    ON CONFLICT (game_id, ply_number) DO NOTHING;
    """
)


def parse_time_control(tc_raw: str) -> tuple[int | None, int]:
    """Extract base time in seconds and increment in seconds from a PGN TimeControl tag."""
    if not tc_raw or tc_raw == "-":
        return None, 0
    if "/" in tc_raw:
        parts = tc_raw.split("/")
        return (int(parts[1]) if parts[1].isdigit() else None), 0
    if "+" in tc_raw:
        base_str, inc_str = tc_raw.split("+", 1)
        base_sec = int(base_str) if base_str.isdigit() else None
        inc_sec = int(inc_str) if inc_str.isdigit() else 0
        return base_sec, inc_sec
    return (int(tc_raw) if tc_raw.isdigit() else None), 0


def parse_clock_comment(comment: str) -> float | None:
    """Extract remaining clock time in seconds from a PGN [%clk H:MM:SS] annotation."""
    if not comment:
        return None
    match = re.search(r"\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]", comment)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def resolve_user_perspective(
    white_user: str,
    black_user: str,
    white_elo: int | None,
    black_elo: int | None,
    result_str: str,
    chess_username: str,
) -> tuple[str | None, int | None, int | None, str]:
    """Determine user_color, user_elo, opponent_elo, and user_outcome for the target player."""
    if white_user.lower() == chess_username.lower():
        outcome_map = {"1-0": "win", "0-1": "loss", "1/2-1/2": "draw"}
        return "white", white_elo, black_elo, outcome_map.get(result_str, "other")

    if black_user.lower() == chess_username.lower():
        outcome_map = {"0-1": "win", "1-0": "loss", "1/2-1/2": "draw"}
        return "black", black_elo, white_elo, outcome_map.get(result_str, "other")

    return None, None, None, "other"


def extract_moves_and_opening(
    game: chess.pgn.Game,
    opening_lookup: dict[str, tuple[str, str]],
) -> tuple[list[dict], str, str | None, str | None, int]:
    """
    Replay a PGN game on a virtual board to collect move records, formatted PGN text,
    deepest matched ECO code, opening name, and total plies.
    """
    board = game.board()
    move_rows: list[dict] = []
    san_tokens: list[str] = []

    detected_eco = game.headers.get("ECO")
    detected_name = game.headers.get("Opening")

    ply = 0
    node = game

    while node.variations:
        next_node = node.variation(0)
        move = next_node.move
        ply += 1

        turn_color = "w" if board.turn == chess.WHITE else "b"
        move_number = board.fullmove_number
        fen_before_norm = normalize_fen(board.fen())
        san_move = board.san(move)
        uci_move = move.uci()

        board.push(move)
        fen_after_norm = normalize_fen(board.fen())
        clock_sec = parse_clock_comment(next_node.comment)

        if fen_after_norm in opening_lookup:
            detected_eco, detected_name = opening_lookup[fen_after_norm]

        if turn_color == "w":
            san_tokens.append(f"{move_number}. {san_move}")
        else:
            san_tokens.append(san_move)

        move_rows.append(
            {
                "ply_number": ply,
                "move_number": move_number,
                "turn_color": turn_color,
                "san_move": san_move,
                "uci_move": uci_move,
                "fen_before_norm": fen_before_norm,
                "fen_after_norm": fen_after_norm,
                "clock_rem_sec": clock_sec,
            }
        )
        node = next_node

    result_str = game.headers.get("Result", "*")
    pgn_moves_raw = " ".join(san_tokens)
    if result_str != "*":
        pgn_moves_raw = f"{pgn_moves_raw} {result_str}".strip()

    return move_rows, pgn_moves_raw, detected_eco, detected_name, ply


def load_single_pgn(
    engine: Engine,
    pgn_path: Path,
    game_type: str,
    chess_username: str,
    opening_lookup: dict[str, tuple[str, str]],
) -> tuple[int, int]:
    """Parse a single PGN file and insert its games and moves into PostgreSQL."""
    if not pgn_path.exists():
        logger.warning("PGN file not found at %s", pgn_path)
        return 0, 0

    games_inserted = 0
    moves_inserted = 0

    with open(pgn_path, "r", encoding="utf-8", errors="replace") as pgn_file, engine.begin() as connection:
        while True:
            game = chess.pgn.read_game(pgn_file)
            if game is None:
                break

            headers = game.headers
            white_user = headers.get("White", "Unknown")
            black_user = headers.get("Black", "Unknown")

            date_raw = headers.get("Date", "1970.01.01").replace(".", "-")
            if "?" in date_raw:
                date_raw = "1970-01-01"

            end_time_raw = headers.get("EndTime", "")
            end_time_utc = end_time_raw.split(" ")[0] if end_time_raw else None

            result_str = headers.get("Result", "*")
            if result_str not in ("1-0", "0-1", "1/2-1/2", "*"):
                result_str = "*"

            white_elo = int(headers["WhiteElo"]) if headers.get("WhiteElo", "").isdigit() else None
            black_elo = int(headers["BlackElo"]) if headers.get("BlackElo", "").isdigit() else None

            user_color, user_elo, opp_elo, user_outcome = resolve_user_perspective(
                white_user=white_user,
                black_user=black_user,
                white_elo=white_elo,
                black_elo=black_elo,
                result_str=result_str,
                chess_username=chess_username,
            )

            tc_raw = headers.get("TimeControl", "-")
            base_sec, inc_sec = parse_time_control(tc_raw)

            move_rows, pgn_moves_raw, detected_eco, detected_name, total_plies = extract_moves_and_opening(
                game=game,
                opening_lookup=opening_lookup,
            )

            unique_signature = f"{white_user}|{black_user}|{date_raw}|{end_time_utc}|{pgn_moves_raw[:120]}"
            game_hash = hashlib.sha256(unique_signature.encode("utf-8")).hexdigest()

            result_proxy = connection.execute(
                INSERT_GAME_SQL,
                {
                    "game_hash": game_hash,
                    "game_type": game_type,
                    "event": headers.get("Event", "Live Chess"),
                    "site": headers.get("Site", "Chess.com"),
                    "played_date": date_raw,
                    "end_time_utc": end_time_utc,
                    "round": headers.get("Round", "-"),
                    "white_username": white_user,
                    "black_username": black_user,
                    "white_elo": white_elo,
                    "black_elo": black_elo,
                    "user_color": user_color,
                    "user_elo": user_elo,
                    "opponent_elo": opp_elo,
                    "user_outcome": user_outcome,
                    "result": result_str,
                    "time_control_raw": tc_raw,
                    "base_time_sec": base_sec,
                    "increment_sec": inc_sec,
                    "termination": headers.get("Termination"),
                    "eco_code": detected_eco,
                    "opening_name": detected_name,
                    "total_plies": total_plies,
                    "pgn_moves_raw": pgn_moves_raw,
                },
            )

            game_id = result_proxy.scalar()
            if game_id is not None and move_rows:
                for move_record in move_rows:
                    move_record["game_id"] = game_id
                connection.execute(INSERT_MOVES_SQL, move_rows)
                games_inserted += 1
                moves_inserted += len(move_rows)

    logger.info(
        "Category '%s' (%s): inserted %d games and %d moves",
        game_type,
        pgn_path.name,
        games_inserted,
        moves_inserted,
    )
    return games_inserted, moves_inserted


def load_all_chess_games(
    engine: Engine,
    games_dir: Path,
    chess_username: str,
    opening_lookup: dict[str, tuple[str, str]],
    categories: list[str] | None = None,
) -> dict[str, tuple[int, int]]:
    """Iterate over all PGN category files and load them into games and game_moves."""
    target_categories = categories or ["blitz", "rapid", "bullet", "daily", "bot"]
    summary: dict[str, tuple[int, int]] = {}

    for category in target_categories:
        pgn_path = games_dir / f"{category}.pgn"
        summary[category] = load_single_pgn(
            engine=engine,
            pgn_path=pgn_path,
            game_type=category,
            chess_username=chess_username,
            opening_lookup=opening_lookup,
        )

    return summary