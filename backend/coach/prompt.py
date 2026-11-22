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
- Order: stored games (postgres tools), then the position graph (neo4j tools), then fresh Stockfish analysis. Use validate_line before citing a continuation longer than the engine's own principal variation.
- Engine scores are from the side to move at the root. Say "mate in N" for mate scores. Cite the depth only from limit.value in the tool result.
- A stored evaluation (cp_loss, best_move_uci in the games) is historical; a Stockfish call is fresh. Do not mix them up.
- Endgame type is not stored on games: never claim an endgame weakness from the coaching brief.
- If a tool fails or returns nothing that the question needed, say that evidence is missing in one clause and stop. Do not fill the gap.

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


def user_turn(request: CoachRequest) -> str:
    """The text of the user turn: board context first, then the question."""
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
    lines += ["", request.question.strip()]
    return "\n".join(lines)


def conversation(request: CoachRequest) -> list[dict[str, str]]:
    """Prior text turns (no tool traffic) followed by the new user turn."""
    messages: list[dict[str, str]] = []
    for turn in request.history:
        role = "user" if turn.role == "user" else "assistant"
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + turn.text
        else:
            messages.append({"role": role, "content": turn.text})
    # The API needs the conversation to start with a user turn.
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] += "\n\n" + user_turn(request)
    else:
        messages.append({"role": "user", "content": user_turn(request)})
    return messages
