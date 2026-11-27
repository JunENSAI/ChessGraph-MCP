"""The coach's tools: the MCP tool contracts, run in-process on the repositories.

Each tool keeps the name and meaning of its MCP counterpart in `chess_mcp/`,
calls the same repository method, and returns JSON. Inputs are validated with
Pydantic before anything runs, and limits are tighter than the MCP servers'
because the answer has to fit a chat reply.

Player names never leave this process: before a result is returned, the data
owner's account is replaced with ``you`` and every other username with
``opponent``. The owner is never a tool argument; it comes from
``CHESS_USERNAME``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from chess_mcp.neo4j.repository import Neo4jRepository
from chess_mcp.postgres.models import GameType, UserOutcome
from chess_mcp.postgres.repository import PostgresRepository
from chess_mcp.stockfish.engine import StockfishService

Source = Literal["postgres", "neo4j", "stockfish"]

USERNAME_KEYS = ("username", "white_username", "black_username")


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoInput(_Input):
    pass


class FenInput(_Input):
    fen: str = Field(description="Position as a FEN; the four-field normalized form is accepted.")


class FenLimitInput(FenInput):
    limit: int = Field(default=10, ge=1, le=20)


class PositionMovesInput(FenLimitInput):
    by: Literal["all", "theory", "owner", "opponent"] = Field(
        default="all", description="theory = book moves; owner = the player's moves; opponent = opponents' moves."
    )


class TheoryExitsInput(_Input):
    limit: int = Field(default=10, ge=1, le=20)
    by: Literal["all", "owner", "opponent"] = Field(default="owner", description="Who played the first non-book move.")


class ListGamesInput(_Input):
    game_type: GameType | None = None
    user_outcome: UserOutcome | None = None
    eco_code: str | None = Field(default=None, max_length=10)
    limit: int = Field(default=5, ge=1, le=10)


class GameMovesInput(_Input):
    game_id: int = Field(ge=1)
    start_ply: int = Field(default=1, ge=1)
    limit: int = Field(default=40, ge=1, le=60)


class BlundersInput(_Input):
    game_id: int | None = Field(default=None, ge=1)
    minimum_cp_loss: int = Field(default=100, ge=0)
    limit: int = Field(default=5, ge=1, le=10)


class AnalyzeInput(FenInput):
    multipv: int = Field(default=1, ge=1, le=3)
    depth: int | None = Field(default=None, ge=1, description="Search depth in plies; the server default when omitted.")


class CompareInput(FenInput):
    played_move_uci: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")
    depth: int | None = Field(default=None, ge=1)


class ValidateInput(FenInput):
    moves_uci: list[str] = Field(min_length=1, max_length=16)


@dataclass
class ToolContext:
    """Where the tools read from. Getters let Neo4j and Stockfish start lazily."""

    postgres: Callable[[], PostgresRepository]
    neo4j: Callable[[], Neo4jRepository]
    stockfish: Callable[[], StockfishService]
    player: str


@dataclass(frozen=True)
class CoachTool:
    name: str
    source: Source
    description: str
    input_model: type[_Input]
    handler: Callable[[ToolContext, Any], Any]


@dataclass(frozen=True)
class ToolOutcome:
    ok: bool
    content: str
    data: Any = None


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    return value


def redact(value: Any, owner: str) -> Any:
    """Replace usernames: the owner becomes ``you``, anyone else ``opponent``."""
    owner_key = owner.strip().casefold()

    def label(name: Any) -> Any:
        if not isinstance(name, str):
            return name
        return "you" if name.strip().casefold() == owner_key else "opponent"

    def walk(item: Any) -> Any:
        if isinstance(item, list):
            return [walk(entry) for entry in item]
        if not isinstance(item, dict):
            return item
        names = {
            str(item[key]): label(item[key])
            for key in USERNAME_KEYS
            if isinstance(item.get(key), str) and item[key]
        }
        result = {}
        for key, entry in item.items():
            if key in USERNAME_KEYS:
                result[key] = label(entry)
            elif isinstance(entry, str):
                for name, replacement in names.items():
                    entry = re.sub(re.escape(name), replacement, entry, flags=re.IGNORECASE)
                result[key] = entry
            else:
                result[key] = walk(entry)
        return result

    cleaned = walk(value)
    if owner_key:
        # Last line of defence for free text the walk did not tie to a name key.
        text = json.dumps(cleaned)
        if owner_key in text.casefold():
            text = re.sub(re.escape(owner.strip()), "you", text, flags=re.IGNORECASE)
            cleaned = json.loads(text)
    return cleaned


def _player_summary(ctx: ToolContext, _: NoInput) -> Any:
    return ctx.postgres().get_player_summary(ctx.player)


def _coaching_brief(ctx: ToolContext, _: NoInput) -> Any:
    return ctx.postgres().get_coaching_brief(ctx.player)


def _list_games(ctx: ToolContext, args: ListGamesInput) -> Any:
    return {
        "games": ctx.postgres().list_games(
            player=ctx.player,
            game_type=args.game_type,
            user_outcome=args.user_outcome,
            eco_code=args.eco_code,
            limit=args.limit,
        )
    }


def _game_moves(ctx: ToolContext, args: GameMovesInput) -> Any:
    return {
        "game_id": args.game_id,
        "moves": ctx.postgres().get_game_moves(
            args.game_id, start_ply=args.start_ply, limit=args.limit
        ),
    }


def _blunders(ctx: ToolContext, args: BlundersInput) -> Any:
    return {
        "blunders": ctx.postgres().get_blunders(
            player=ctx.player,
            game_id=args.game_id,
            minimum_cp_loss=args.minimum_cp_loss,
            limit=args.limit,
        )
    }


def _occurrences(ctx: ToolContext, args: FenLimitInput) -> Any:
    fen, rows = ctx.postgres().find_position_occurrences(args.fen, limit=args.limit)
    return {"normalized_fen": fen, "occurrences": rows}


def _lookup_opening(ctx: ToolContext, args: FenInput) -> Any:
    fen, rows = ctx.postgres().lookup_opening(args.fen, limit=5)
    return {"normalized_fen": fen, "openings": rows}


def _position_context(ctx: ToolContext, args: FenInput) -> Any:
    return ctx.neo4j().get_position_context(args.fen)


def _position_moves(ctx: ToolContext, args: PositionMovesInput) -> Any:
    return ctx.neo4j().get_position_moves(args.fen, args.limit, args.by)


def _games_through(ctx: ToolContext, args: FenLimitInput) -> Any:
    return ctx.neo4j().get_games_through_position(args.fen, args.limit)


def _theory_exits(ctx: ToolContext, args: TheoryExitsInput) -> Any:
    return ctx.neo4j().get_theory_exits(args.limit, args.by)


def _analyze(ctx: ToolContext, args: AnalyzeInput) -> Any:
    return ctx.stockfish().analyze_position(
        args.fen, limit_type="depth", limit_value=args.depth, multipv=args.multipv
    )


def _compare(ctx: ToolContext, args: CompareInput) -> Any:
    return ctx.stockfish().compare_move(
        args.fen, args.played_move_uci, limit_type="depth", limit_value=args.depth
    )


def _validate(ctx: ToolContext, args: ValidateInput) -> Any:
    return ctx.stockfish().validate_line(args.fen, args.moves_uci)


TOOLS: tuple[CoachTool, ...] = (
    CoachTool("get_player_summary", "postgres", "Overall record of the player: games, wins, draws, losses, average ratings, date range.", NoInput, _player_summary),
    CoachTool("get_coaching_brief", "postgres", "Strongest opening families, the weakest target family with repeated mistakes, and four training tasks, from the stored games. Call first for training, weakness, strength or opening questions.", NoInput, _coaching_brief),
    CoachTool("list_games", "postgres", "The player's most recent stored games, filtered by time control, outcome or ECO code.", ListGamesInput, _list_games),
    CoachTool("get_game_moves", "postgres", "Ordered moves of one stored game with FEN before/after, clock, stored evaluations, centipawn loss and the stored engine move.", GameMovesInput, _game_moves),
    CoachTool("get_blunders", "postgres", "The player's own largest evaluated mistakes, optionally for one game, largest first.", BlundersInput, _blunders),
    CoachTool("find_position_occurrences", "postgres", "Stored games where this exact position occurred, and the move played there.", FenLimitInput, _occurrences),
    CoachTool("lookup_opening", "postgres", "Named opening theory that reaches exactly this position.", FenInput, _lookup_opening),
    CoachTool("get_position_context", "neo4j", "The position in the graph: phase, material, average stored eval from the side to move, games that reached it, exact opening, opening families whose lines pass through it, endgame type and the stored engine best move.", FenInput, _position_context),
    CoachTool("get_position_moves", "neo4j", "Moves leaving this position, most-played first: played moves (PLAYED_MOVE) split by mover, by = owner (the player) or opponent, each with the mover's wins/draws/losses, score_pct, average centipawn loss and severity counts; then theory moves (THEORY_MOVE). Pass by = theory, owner or opponent to list one kind.", PositionMovesInput, _position_moves),
    CoachTool("get_games_through_position", "neo4j", "The player's games that reached this position, newest first, with the player's wins, draws and losses from it.", FenLimitInput, _games_through),
    CoachTool("get_theory_exits", "neo4j", "Where the player's games leave opening theory most often: the position, the first non-book move, who played it, the book moves there and the player's score. book_ended = true means the opening data has no move there, so the line ended rather than being left.", TheoryExitsInput, _theory_exits),
    CoachTool("analyze_position", "stockfish", "Fresh Stockfish analysis: score from the side to move, best move and principal variation in UCI and SAN. limit.value in the result is the depth searched.", AnalyzeInput, _analyze),
    CoachTool("compare_move", "stockfish", "Compare a played move with Stockfish's best move from the same position and the same budget; returns both scores and the centipawn loss.", CompareInput, _compare),
    CoachTool("validate_line", "stockfish", "Replay a UCI line from a position and return legal SAN and the FEN after each move. Use before citing any continuation.", ValidateInput, _validate),
)

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def _schema(model: type[_Input]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    schema.setdefault("properties", {})
    schema["additionalProperties"] = False
    return schema


def tool_definitions() -> list[dict[str, Any]]:
    """Tool definitions for the Messages API, in a fixed order for prompt caching."""
    return [
        {"name": tool.name, "description": tool.description, "input_schema": _schema(tool.input_model)}
        for tool in TOOLS
    ]


def run_tool(name: str, raw_input: Any, ctx: ToolContext) -> ToolOutcome:
    """Validate, run, redact and serialize one tool call. Never raises."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return ToolOutcome(False, f"Unknown tool {name!r}.")
    try:
        args = tool.input_model.model_validate(raw_input if isinstance(raw_input, dict) else {})
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'input'}: {error['msg']}"
            for error in exc.errors()
        )
        return ToolOutcome(False, f"Invalid input for {name}: {problems}")
    try:
        data = redact(_dump(tool.handler(ctx, args)), ctx.player)
    except (ValueError, LookupError) as exc:
        return ToolOutcome(False, f"{name}: {exc}")
    except Exception as exc:  # noqa: BLE001 - a down store is evidence that is missing
        return ToolOutcome(False, f"{name}: {tool.source} is unavailable ({type(exc).__name__}).")
    return ToolOutcome(True, json.dumps(data, default=str), data)


# --------------------------------------------------------------------------- graph context

GRAPH_CONTEXT_CHARS = 6000
STAT_KEYS = ("games", "wins", "draws", "losses", "score_pct", "avg_cp_loss", "mistakes", "blunders", "is_engine_best")


def _compact_move(move: Any) -> dict[str, Any]:
    row = {"move": move.san_move or move.uci_move, "uci": move.uci_move}
    row.update({key: getattr(move, key) for key in STAT_KEYS if getattr(move, key) not in (None, 0, False)})
    return row


def style_summary(context: Any) -> dict[str, Any]:
    """The owner's record around a position, reduced to what a coaching answer cites."""
    position = context.position
    summary: dict[str, Any] = {"fen": context.fen_norm}
    if position is not None:
        summary["position"] = {
            key: getattr(position, key)
            for key in ("phase", "eval_cp", "best_move_san")
            if getattr(position, key) is not None
        }
    if context.opening:
        summary["opening"] = context.opening
    if context.opening_families:
        summary["opening_families"] = context.opening_families
    summary["your_games_here"] = {
        "games": context.total_games,
        "wins": context.owner_wins,
        "draws": context.owner_draws,
        "losses": context.owner_losses,
    }
    summary["your_moves"] = [_compact_move(move) for move in context.owner_moves]
    summary["opponent_moves"] = [_compact_move(move) for move in context.opponent_moves]
    summary["book_moves"] = [move.san_move or move.uci_move for move in context.theory_moves]
    summary["recent_games"] = [
        {
            "game_id": visit.game.game_id,
            "date": visit.game.played_date,
            "type": visit.game.game_type,
            "your_color": visit.game.user_color,
            "result": visit.game.user_outcome,
        }
        for visit in context.recent_games
    ]
    summary["nearby_mistakes"] = [
        {
            "fen": item.position.fen_norm,
            "plies_away": item.distance,
            "games": item.games,
            "average_cp_loss": round(item.average_cp_loss) if item.average_cp_loss is not None else None,
            "you_played": item.played_moves,
            "stored_engine_moves": item.best_moves,
        }
        for item in context.nearby_mistakes
    ]
    return summary


def read_style_context(fen: str, ctx: ToolContext) -> Any | None:
    """The owner's record around ``fen`` from the graph, or None when Neo4j fails."""
    try:
        return ctx.neo4j().get_style_context(fen)
    except Exception:  # noqa: BLE001 - missing graph evidence, not a failed answer
        return None


def graph_context(context: Any | None, ctx: ToolContext) -> str | None:
    """Compact, redacted JSON of a style context, or None without one.

    At most GRAPH_CONTEXT_CHARS: nearby mistakes, then recent games, then
    opponent moves are dropped from the end until it fits.
    """
    if context is None:
        return None
    summary = redact(style_summary(context), ctx.player)
    text = json.dumps(summary, separators=(",", ":"), default=str)
    for key in ("nearby_mistakes", "recent_games", "opponent_moves"):
        while len(text) > GRAPH_CONTEXT_CHARS and summary[key]:
            summary[key].pop()
            text = json.dumps(summary, separators=(",", ":"), default=str)
    return text if len(text) <= GRAPH_CONTEXT_CHARS else None


# --------------------------------------------------------------------------- candidate lines

CANDIDATE_LINES = 3
LINE_PLIES = 6


def rank_lines(analysis: dict[str, Any], games: dict[str, int], book: set[str]) -> dict[str, Any] | None:
    """Stockfish's lines in rank order, each tagged with how people play its first move.

    ``games`` counts stored games per first move (yours and your opponents'),
    ``book`` holds the book moves. The ``human`` line is the most played one;
    with no games, the best-ranked book line; with neither, no line.
    """
    lines = []
    for index, line in enumerate(analysis.get("lines") or [], start=1):
        uci = (line.get("pv") or {}).get("uci") or []
        if not uci:
            continue
        lines.append(
            {
                "rank": index,
                "uci": uci[:LINE_PLIES],
                "san": ((line.get("pv") or {}).get("san") or [])[:LINE_PLIES],
                "score": line.get("score"),
                "games": games.get(uci[0], 0),
                "book": uci[0] in book,
                "human": False,
            }
        )
    if not lines:
        return None
    played = [line for line in lines if line["games"] > 0]
    booked = [line for line in lines if line["book"]]
    if played:
        max(played, key=lambda line: line["games"])["human"] = True
    elif booked:
        booked[0]["human"] = True
    return {
        "root_player": analysis.get("root_player"),
        "depth": (analysis.get("limit") or {}).get("value"),
        "lines": lines,
    }


def candidate_lines(fen: str, ctx: ToolContext, context: Any | None) -> dict[str, Any] | None:
    """Stockfish's top 3 lines from ``fen``, tagged from the style context; None if Stockfish fails."""
    try:
        analysis = _dump(
            ctx.stockfish().analyze_position(fen, limit_type="depth", limit_value=None, multipv=CANDIDATE_LINES)
        )
    except Exception:  # noqa: BLE001 - missing engine evidence, not a failed answer
        return None
    games: dict[str, int] = {}
    book: set[str] = set()
    if context is not None:
        for move in [*context.owner_moves, *context.opponent_moves]:
            games[move.uci_move] = games.get(move.uci_move, 0) + (move.games or 0)
        book = {move.uci_move for move in context.theory_moves}
    return rank_lines(analysis, games, book)


def lines_text(lines: dict[str, Any] | None) -> str | None:
    """The candidate lines as compact JSON for the prompt (SAN only), or None."""
    if not lines:
        return None
    block = {
        "side_to_move": lines.get("root_player"),
        "depth": lines.get("depth"),
        "lines": [
            {key: line[key] for key in ("rank", "san", "score", "games", "book", "human")}
            for line in lines["lines"]
        ],
    }
    return json.dumps(block, separators=(",", ":"), default=str)

# --------------------------------------------------------------------------- player profile


def style_profile(ctx: ToolContext) -> str | None:
    """The player's record, best and weakest opening families, and top repeated mistake.

    Compact, redacted JSON, or None when PostgreSQL fails.
    """
    try:
        summary = _dump(ctx.postgres().get_player_summary(ctx.player))
        brief = _dump(ctx.postgres().get_coaching_brief(ctx.player))
    except Exception:  # noqa: BLE001 - missing evidence, not a failed answer
        return None

    def record(row: dict[str, Any]) -> dict[str, Any]:
        return {key: row.get(key) for key in ("family", "games", "wins", "draws", "losses") if row.get(key) is not None}

    profile: dict[str, Any] = {
        "record": {
            key: summary.get(key)
            for key in ("games_played", "wins", "draws", "losses", "average_rating")
            if summary.get(key) is not None
        },
        "strongest_openings": [record(row) for row in (brief.get("strengths") or [])[:3]],
    }
    target = brief.get("target")
    if target:
        profile["weakest_opening"] = record(target)
        splits = target.get("splits") or []
        if splits:
            split = splits[0]
            profile["repeated_mistake"] = {
                key: split.get(key)
                for key in ("ply", "played_san", "best_san", "times", "average_cp_loss")
                if split.get(key) is not None
            }
    return json.dumps(redact(profile, ctx.player), separators=(",", ":"), default=str)
