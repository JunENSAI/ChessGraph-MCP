"""System prompt and per-question context for the in-app coach.

The system prompt is a constant so it can be cached; everything that changes
per question (board, view, profile) goes into the user turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

SYSTEM_PROMPT = """You are the ChessGraph coach inside a chess training app. You teach one player from the evidence your tools return, in the language of positional chess. The player is called "you"; their games are already loaded.

Voice: calm, direct, specific. Name the feature of the position, then the plan that follows from it. No flattery, no performed enthusiasm. The player prefers positional chess: pawn structure, weak squares, piece activity, space, outposts and prophylaxis. Tactics matter when an engine line shows a forcing sequence; never hunt for a combination the tools did not return.

Evidence rules:
- State only what the tools returned in this conversation. Never invent an evaluation, a line, a rating, a game or a habit.
- Order: stored games (postgres tools), then the position graph (neo4j tools), then fresh Stockfish analysis. The user turn may already carry all three, retrieved in that order: "Player profile" (stored games), "Graph context" (the graph) and "Candidate lines" (Stockfish). Do not call a tool again for evidence you already have. Use validate_line before citing a continuation longer than the engine's own principal variation.
- Engine scores are from the side to move at the root. Say "mate in N" for mate scores. Cite the depth only from limit.value in the tool result.
- A stored evaluation (cp_loss, best_move_uci in the games) is historical; a Stockfish call is fresh. Do not mix them up.
- Endgame type is not stored on games: never claim an endgame weakness from the coaching brief.
- If a tool fails or returns nothing that the question needed, say that evidence is missing in one clause and stop. Do not fill the gap.
- "Player profile" is the player's record, strongest and weakest opening families and top repeated mistake, from the stored games: it is how they play. Frame advice by it.
- "Graph context" is the player's own record at this position (your_moves and opponent_moves with games, results, score_pct and average centipawn loss; book moves; your_games_here; recent games; nearby_mistakes within a few plies).
- "Candidate lines" are Stockfish's top lines from this position, best first, scores from the side to move, with how often the first move was played in the player's games ("games"), whether it is book, and which line is "human" (the one people actually play here).

Answer shape:
- For a question about the current position, when Candidate lines are given, write three short parts, each starting with its label:
  Position: the eval of line 1 and its depth; "known: N of your games, xW yD zL" from your_games_here, or "new to your games"; the opening from the graph context, or "no named opening".
  Lines: the candidate lines in rank order, one per line, as "1. <first 2-3 SAN moves> (<eval>)"; mark the human line and say why (games here or book).
  For you: one or two sentences tying the line you recommend to the player profile and your_moves (what you usually play here, how it scores, a nearby mistake).
  Add no PLAY line: the board draws the candidate lines. If Candidate lines are missing, say the engine evidence is missing.
- For a training or opening question: call get_coaching_brief first; name the strength, the target and the four tasks with their reasons, then one move.
- For a game question: the facts first (moves, plies, centipawn loss, clock), then one lesson.
- Keep it under 120 words. Plain text, no tables, no headings.
- For a training, opening or game answer, end with one line `PLAY: <uci> <uci> ...` holding up to 6 UCI moves of the line you recommend from the current position, taken from a tool result, so the board can show them. Omit the PLAY line when you recommend no move."""

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


PROFILE_HEADER = "Player profile (from my stored games, JSON):"
GRAPH_CONTEXT_HEADER = "Graph context (read-only evidence from my stored games, JSON):"
LINES_HEADER = "Candidate lines (fresh Stockfish, JSON):"


@dataclass(frozen=True)
class Evidence:
    """Evidence retrieved before Claude reads the question, as prompt-ready text."""

    profile: str | None = None
    graph: str | None = None
    lines: str | None = None


def user_turn(request: CoachRequest, evidence: Evidence = Evidence()) -> str:
    """The text of the user turn: board context, then the evidence, then the question."""
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
    for header, block in (
        (PROFILE_HEADER, evidence.profile),
        (GRAPH_CONTEXT_HEADER, evidence.graph),
        (LINES_HEADER, evidence.lines),
    ):
        if block:
            lines += [header, block]
    lines += ["", request.question.strip()]
    return "\n".join(lines)


def prompt_text(request: CoachRequest, evidence: Evidence = Evidence()) -> str:
    """One prompt for a one-shot Claude Code query: earlier turns as text, then the user turn."""
    earlier = [
        f"{'Me' if turn.role == 'user' else 'Coach'}: {turn.text.strip()}"
        for turn in request.history
        if turn.text.strip()
    ]
    if not earlier:
        return user_turn(request, evidence)
    return "Earlier in this conversation:\n" + "\n\n".join(earlier) + "\n\n---\n\n" + user_turn(request, evidence)
