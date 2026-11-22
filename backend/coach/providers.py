"""Coach providers. Each turns a CoachRequest into a stream of events.

Events are plain dicts sent to the browser as server-sent events:

- ``{"type": "start", "mode": "claude" | "offline", "model": str | None}``
- ``{"type": "tool_start", "tool": name, "source": "postgres" | "neo4j" | "stockfish"}``
- ``{"type": "tool_end", "tool": name, "source": ..., "ok": bool}``
- ``{"type": "text", "text": str}`` (appended in order)
- ``{"type": "done", "mode": ..., "stop_reason": str}``
- ``{"type": "error", "message": str}`` (followed by nothing)

``ClaudeProvider`` runs a manual tool loop over the Messages API, so every
tool call can be reported as it happens. ``OfflineProvider`` needs no key: it
runs a fixed, deterministic plan of the same tools and renders their results
from a template. It is labelled as offline in its answer.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Protocol

from .prompt import SYSTEM_PROMPT, CoachRequest, conversation
from .tools import TOOLS_BY_NAME, ToolContext, ToolOutcome, run_tool, tool_definitions

Event = dict[str, Any]

FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_MODEL = "claude-opus-5-5"
OFFLINE_NOTE = (
    "Offline evidence mode: these are the tool results without a written "
    "explanation. Set ANTHROPIC_API_KEY in .env for the Claude coach."
)


class CoachProvider(Protocol):
    mode: str

    def run(self, request: CoachRequest, ctx: ToolContext) -> Iterator[Event]: ...


def _tool_events(name: str, raw_input: Any, ctx: ToolContext) -> Iterator[Event | ToolOutcome]:
    source = TOOLS_BY_NAME[name].source if name in TOOLS_BY_NAME else "postgres"
    yield {"type": "tool_start", "tool": name, "source": source}
    outcome = run_tool(name, raw_input, ctx)
    yield {"type": "tool_end", "tool": name, "source": source, "ok": outcome.ok}
    yield outcome


# --------------------------------------------------------------------------- Claude


class ClaudeProvider:
    """Claude Messages API with a manual, streamed tool loop."""

    mode = "claude"

    def __init__(
        self,
        client: Any,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = "low",
        refusal_fallback: bool = True,
        max_iterations: int = 8,
        max_tokens: int = 16_000,
    ) -> None:
        self.client = client
        self.model = model
        self.effort = effort
        self.refusal_fallback = refusal_fallback
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens

    def _stream(self, messages: list[dict[str, Any]]) -> Any:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "tools": tool_definitions(),
            "messages": messages,
            "output_config": {"effort": self.effort},
            # Automatic prompt caching: system prompt and tools never change.
            "cache_control": {"type": "ephemeral"},
        }
        if self.refusal_fallback:
            # On a policy decline the API re-runs the turn on a fallback model.
            return self.client.beta.messages.stream(
                betas=[FALLBACK_BETA], fallbacks="default", **params
            )
        return self.client.messages.stream(**params)

    def run(self, request: CoachRequest, ctx: ToolContext) -> Iterator[Event]:
        yield {"type": "start", "mode": self.mode, "model": self.model}
        messages: list[dict[str, Any]] = conversation(request)
        try:
            for _ in range(self.max_iterations):
                with self._stream(messages) as stream:
                    for event in stream:
                        if getattr(event, "type", None) == "text" and event.text:
                            yield {"type": "text", "text": event.text}
                    final = stream.get_final_message()

                stop = final.stop_reason
                if stop == "refusal":
                    yield {"type": "error", "message": "Claude declined to answer this question."}
                    return
                if stop == "pause_turn":
                    messages.append({"role": "assistant", "content": final.content})
                    continue
                tool_uses = [block for block in final.content if block.type == "tool_use"]
                if not tool_uses:
                    yield {"type": "done", "mode": self.mode, "stop_reason": stop or "end_turn"}
                    return
                if stop == "max_tokens":
                    yield {"type": "error", "message": "The answer was cut off before a tool call finished."}
                    return

                results = []
                for block in tool_uses:
                    outcome: ToolOutcome | None = None
                    for item in _tool_events(block.name, block.input, ctx):
                        if isinstance(item, ToolOutcome):
                            outcome = item
                        else:
                            yield item
                    assert outcome is not None
                    result: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": outcome.content,
                    }
                    if not outcome.ok:
                        result["is_error"] = True
                    results.append(result)
                # All results of one turn go back in a single user message.
                messages.append({"role": "assistant", "content": final.content})
                messages.append({"role": "user", "content": results})

            yield {"type": "text", "text": "\n\nI stopped after the maximum number of tool rounds."}
            yield {"type": "done", "mode": self.mode, "stop_reason": "max_iterations"}
        except Exception as exc:  # noqa: BLE001 - mapped to a safe message below
            yield {"type": "error", "message": api_error_message(exc)}


def api_error_message(exc: Exception) -> str:
    """A user-facing message that never includes the key or request body."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is installed
        return "The coach failed."
    if isinstance(exc, anthropic.AuthenticationError):
        return "Anthropic rejected ANTHROPIC_API_KEY. Check the key in .env and restart the API."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "This API key has no access to the configured model (CLAUDE_MODEL)."
    if isinstance(exc, anthropic.NotFoundError):
        return "The configured model (CLAUDE_MODEL) was not found."
    if isinstance(exc, anthropic.RateLimitError):
        return "The Claude API is rate limiting requests. Wait a moment and ask again."
    if isinstance(exc, anthropic.BadRequestError):
        return "The Claude API rejected the request (HTTP 400). See the API log for details."
    if isinstance(exc, anthropic.APIStatusError):
        return f"The Claude API failed (HTTP {exc.status_code}). Try again."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach the Claude API. Check the network connection."
    return f"The coach failed ({type(exc).__name__})."


# --------------------------------------------------------------------------- Offline


COURSE_QUESTION = re.compile(
    r"\b(train(?:ing)?|weakness(?:es)?|strengths?|openings?|defen[cs]es?|work on|study|practi[cs]e"
    r"|training plan|plan for me|(?:common|repeated|my) mistakes?)\b",
    re.IGNORECASE,
)
GAME_QUESTION = re.compile(r"\b(mistakes?|blunders?|why did i|lose|lost|review|went wrong)\b", re.IGNORECASE)


def format_score(score: dict[str, Any], root_player: str) -> str:
    side = root_player.capitalize()
    if score.get("type") == "mate":
        moves = abs(int(score["value"]))
        return f"mate in {moves} for {side}" if score["value"] > 0 else f"{side} is mated in {moves}"
    pawns = int(score["value"]) / 100
    return f"{pawns:+.2f} for {side} (side to move)"


MATE_LOSS = 5_000


def describe_loss(cp_loss: int) -> str:
    """Stored mate scores are flattened to +/-10000 cp, so a huge loss means a mate swing."""
    if cp_loss >= MATE_LOSS:
        return "a mate swing (the stored scores include a forced mate)"
    return f"{cp_loss} cp lost"


def _record(row: dict[str, Any]) -> str:
    return f"{row.get('wins', 0)}W {row.get('draws', 0)}D {row.get('losses', 0)}L"


class OfflineProvider:
    """No model: a fixed plan of tool calls, rendered as an evidence summary."""

    mode = "offline"

    def run(self, request: CoachRequest, ctx: ToolContext) -> Iterator[Event]:
        yield {"type": "start", "mode": self.mode, "model": None}
        if request.played:
            text = (
                f"Stockfish played {request.played.san} for {request.played.color}. "
                f"Evaluation before the move, from the side to move: {request.played.eval_text}.\n\n"
                + OFFLINE_NOTE
            )
        elif COURSE_QUESTION.search(request.question):
            text = yield from self._course(ctx)
        elif request.game_id is not None and GAME_QUESTION.search(request.question):
            text = yield from self._game(request, ctx)
        else:
            text = yield from self._position(request, ctx)
        yield {"type": "text", "text": text}
        yield {"type": "done", "mode": self.mode, "stop_reason": "end_turn"}

    @staticmethod
    def _call(name: str, args: dict[str, Any], ctx: ToolContext):
        outcome: ToolOutcome | None = None
        for item in _tool_events(name, args, ctx):
            if isinstance(item, ToolOutcome):
                outcome = item
            else:
                yield item
        assert outcome is not None
        return outcome

    def _position(self, request: CoachRequest, ctx: ToolContext):
        analysis = yield from self._call("analyze_position", {"fen": request.fen, "multipv": 1}, ctx)
        graph = yield from self._call("get_position_moves", {"fen": request.fen, "limit": 10}, ctx)
        lines: list[str] = []
        play: list[str] = []
        if analysis.ok and analysis.data.get("lines"):
            best = analysis.data["lines"][0]
            depth = analysis.data["limit"]["value"]
            lines.append(f"EVAL: {format_score(best['score'], analysis.data['root_player'])}, Stockfish depth {depth}.")
            if best.get("move_san"):
                lines.append(f"MOVE: {best['move_san']}")
            pv = best["pv"]["san"][:6]
            if len(pv) > 1:
                lines.append("Line: " + " ".join(pv) + ".")
            play = best["pv"]["uci"][:6]
        else:
            lines.append(f"Stockfish evidence is missing: {analysis.content}")

        if graph.ok:
            moves = graph.data.get("moves", [])
            played = sorted(
                (m for m in moves if m["relationship"] == "PLAYED_MOVE"),
                key=lambda m: m.get("total_games") or 0,
                reverse=True,
            )
            theory = [m.get("san_move") or m["uci_move"] for m in moves if m["relationship"] == "THEORY_MOVE"]
            if played:
                top = played[0]
                lines.append(
                    f"Your games: {sum(m.get('total_games') or 0 for m in played)} moves recorded from here; "
                    f"most often {top.get('san_move') or top['uci_move']} ({top.get('total_games')} times, {_record(top)})."
                )
            else:
                lines.append("Your games: this position is not in your stored games.")
            if theory:
                lines.append("Theory here: " + ", ".join(theory[:5]) + ".")
        else:
            lines.append("Graph evidence is missing (Neo4j did not answer).")

        lines += ["", OFFLINE_NOTE]
        if play:
            lines.append("PLAY: " + " ".join(play))
        return "\n".join(lines)

    def _course(self, ctx: ToolContext):
        brief = yield from self._call("get_coaching_brief", {}, ctx)
        if not brief.ok:
            return f"Coaching evidence is missing: {brief.content}\n\n{OFFLINE_NOTE}"
        data = brief.data
        lines = []
        if data.get("strengths"):
            top = data["strengths"][0]
            lines.append(f"STRENGTH: {top['family']}, {top['games']} games, {_record(top)}.")
        target = data.get("target")
        if target:
            lines.append(f"TARGET: {target['family']}, {target['games']} games, {_record(target)}.")
            if target.get("splits"):
                split = target["splits"][0]
                stored = "a mate" if split.get("mate") else split["best_san"]
                lines.append(
                    f"You played {split['played_san']} at ply {split['ply']} {split['times']} times; "
                    f"the stored engine move is {stored} (average loss {split['average_cp_loss']} cp)."
                )
        else:
            lines.append("TARGET: no opening family has enough games for a target yet.")
        for index, task in enumerate(data.get("tasks", []), start=1):
            lines.append(f"{index}. {task['title']}: {task['reason']}")
        lines += ["", OFFLINE_NOTE]
        return "\n".join(lines)

    def _game(self, request: CoachRequest, ctx: ToolContext):
        found = yield from self._call(
            "get_blunders", {"game_id": request.game_id, "minimum_cp_loss": 100, "limit": 3}, ctx
        )
        if not found.ok:
            return f"Game evidence is missing: {found.content}\n\n{OFFLINE_NOTE}"
        blunders = found.data.get("blunders", [])
        if not blunders:
            return f"No stored mistake of 100 cp or more in game {request.game_id}.\n\n{OFFLINE_NOTE}"
        lines = [f"Largest stored mistakes in game {request.game_id}:"]
        for item in blunders:
            lines.append(
                f"- Move {item['move_number']} {item['san_move']}: {describe_loss(item['cp_loss'])}; "
                f"stored engine move {item.get('best_move_uci') or 'unknown'}."
            )
        worst = blunders[0]
        compared = yield from self._call(
            "compare_move",
            {"fen": worst["fen_before_norm"], "played_move_uci": worst["uci_move"]},
            ctx,
        )
        if compared.ok:
            data = compared.data
            best = data["best"]
            lines.append(
                f"Fresh check of move {worst['move_number']}: Stockfish prefers {best.get('move_san')} "
                f"({format_score(best['score'], data['root_player'])}) over {data['played_move_san']} "
                f"({format_score(data['played']['score'], data['root_player'])}), depth {data['limit']['value']}."
            )
        lines += ["", OFFLINE_NOTE]
        return "\n".join(lines)
