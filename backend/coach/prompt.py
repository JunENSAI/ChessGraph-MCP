"""System prompt and per-question context for the in-app coach.

The system prompt is a constant so it can be cached; everything that changes
per question (board, view, profile) goes into the user turn.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SYSTEM_PROMPT = """You are the ChessGraph coach inside a chess training app. You teach one player from the evidence your tools return, in the language of positional chess. The player is called "you"; their games are already loaded.

Voice: calm, direct, specific. Name the feature of the position, then the plan that follows from it. No flattery, no performed enthusiasm. The player prefers positional chess: pawn structure, weak squares, piece activity, space, outposts and prophylaxis. Tactics matter when an engine line shows a forcing sequence; never hunt for a combination the tools did not return.

Evidence rules:
- State only what the tools returned in this conversation. Never invent an evaluation, a line, a rating, a game or a habit.
- Order: stored games (postgres tools), then the position graph (neo4j tools), then fresh Stockfish analysis. The graph context in the user turn is already retrieved; read it with the stored games, before Stockfish. Use validate_line before citing a continuation longer than the engine's own principal variation.
- Engine scores are from the side to move at the root. Say "mate in N" for mate scores. Cite the depth only from limit.value in the tool result.
- A stored evaluation (cp_loss, best_move_uci in the games) is historical; a Stockfish call is fresh. Do not mix them up.
- Endgame type is not stored on games: never claim an endgame weakness from the coaching brief.
- If a tool fails or returns nothing that the question needed, say that evidence is missing in one clause and stop. Do not fill the gap.
- The user turn may carry "Graph context": the player's own record from the position graph (your_moves and opponent_moves with games, results, score_pct and average centipawn loss; book moves; recent games; nearby_mistakes within a few plies). It is evidence already retrieved: cite it instead of calling get_position_moves or get_games_through_position for the same position.

Answer shape (the app parses the last line):
- For a position question: the evaluation, one move in SAN, and at most two sentences on why.
- For a training or opening question: call get_coaching_brief first; name the strength, the target and the four tasks with their reasons, then one move.
- For a game question: the facts first (moves, plies, centipawn loss, clock), then one lesson.
- Keep it under 120 words. Plain text, no tables, no headings.
- End with one line `PLAY: <uci> <uci> ...` holding up to 6 UCI moves of the line you recommend from the current position, taken from a tool result, so the board can show them. Omit the PLAY line when you recommend no move."""

EXPLAIN_PLAYED_INSTRUCTION = (
    "The board already played this move. Explain only this move in at most two "
    "sentences, from the evaluation given. Do not call tools and do not add a PLAY line."
)


class PlayedMove(BaseModel):
    san: str = Field(max_length=12)
    color: Literal["white", "black"]
    eval_text: str = Field(max_length=40)


class HistoryTurn(BaseModel):
    role: Literal["user", "coach"]
    text: str = Field(max_length=4000)


class CoachRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    fen: str = Field(min_length=1, max_length=120)
    view: Literal["training", "review"] = "training"
    summary: str = Field(default="", max_length=600)
    profile: str = Field(default="", max_length=600)
    game_id: int | None = Field(default=None, ge=1)
    played: PlayedMove | None = None
    history: list[HistoryTurn] = Field(default_factory=list, max_length=12)


GRAPH_CONTEXT_HEADER = "Graph context (read-only evidence from my stored games, JSON):"


def user_turn(request: CoachRequest, graph: str | None = None) -> str:
    """The text of the user turn: board context, then graph context, then the question."""
    subject = "training board" if request.view == "training" else "position from one of my games"
    lines = [f"Current position (FEN): {request.fen}", f"Context: {subject}."]
    if request.summary:
        lines.append(f"Board notes: {request.summary}")
    if request.game_id is not None:
        lines.append(f"Stored game id: {request.game_id}")
    if request.profile:
        lines.append(f"My profile: {request.profile}")
    if request.played:
        lines.append(
            f"Move just played: {request.played.san} by {request.played.color}; "
            f"Stockfish evaluation before it, from the side to move: {request.played.eval_text}."
        )
        lines.append(EXPLAIN_PLAYED_INSTRUCTION)
    if graph:
        lines += [GRAPH_CONTEXT_HEADER, graph]
    lines += ["", request.question.strip()]
    return "\n".join(lines)


def prompt_text(request: CoachRequest, graph: str | None = None) -> str:
    """One prompt for a one-shot Claude Code query: earlier turns as text, then the user turn."""
    earlier = [
        f"{'Me' if turn.role == 'user' else 'Coach'}: {turn.text.strip()}"
        for turn in request.history
        if turn.text.strip()
    ]
    if not earlier:
        return user_turn(request, graph)
    return "Earlier in this conversation:\n" + "\n\n".join(earlier) + "\n\n---\n\n" + user_turn(request, graph)
