"""Coach providers. Each turns a CoachRequest into a stream of events.

Events are plain dicts sent to the browser as server-sent events:

- ``{"type": "start", "mode": "claude" | "offline", "model": str | None}``
- ``{"type": "tool_start", "tool": name, "source": "postgres" | "neo4j" | "stockfish"}``
- ``{"type": "tool_end", "tool": name, "source": ..., "ok": bool}``
- ``{"type": "text", "text": str}`` (appended in order)
- ``{"type": "done", "mode": ..., "stop_reason": str}``
- ``{"type": "error", "message": str}`` (followed by nothing)

``ClaudeProvider`` runs Claude through the local Claude Code login (the
subscription, no API key) with the Agent SDK; the coach tools run in-process
and report each call as it happens. Its ``run`` is an async generator.
``OfflineProvider`` needs no model: it runs a fixed, deterministic plan of the
same tools and renders their results from a template. It is labelled as
offline in its answer.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, Protocol

from claude_agent_sdk import (
    ClaudeAgentOptions,
    CLINotFoundError,
    ProcessError,
    ResultMessage,
    SdkMcpTool,
    StreamEvent,
    create_sdk_mcp_server,
    query,
)

from .prompt import SYSTEM_PROMPT, CoachRequest, prompt_text
from .tools import TOOLS, TOOLS_BY_NAME, ToolContext, ToolOutcome, graph_context, run_tool, tool_definitions

Event = dict[str, Any]

DEFAULT_MODEL = "claude-opus-5-5"
OFFLINE_NOTE = (
    "Offline evidence mode: these are the tool results without a written "
    "explanation. Log in with `claude` and set COACH_MODE=claude in .env for the Claude coach."
)


class CoachProvider(Protocol):
    mode: str

    def run(self, request: CoachRequest, ctx: ToolContext) -> Iterator[Event] | AsyncIterator[Event]: ...


def _tool_events(name: str, raw_input: Any, ctx: ToolContext) -> Iterator[Event | ToolOutcome]:
    source = TOOLS_BY_NAME[name].source if name in TOOLS_BY_NAME else "postgres"
    yield {"type": "tool_start", "tool": name, "source": source}
    outcome = run_tool(name, raw_input, ctx)
    yield {"type": "tool_end", "tool": name, "source": source, "ok": outcome.ok}
    yield outcome


# --------------------------------------------------------------------------- Claude


TOOL_SERVER = "coach"
TOOL_PREFIX = f"mcp__{TOOL_SERVER}__"
LOGIN_HINT = "Claude Code is not logged in. Run `claude` once and use /login, then ask again."
MAX_TURNS_NOTE = "\n\nI stopped after the maximum number of tool rounds."
_END = object()


def coach_tools(ctx: ToolContext, emit: Callable[[Event], None]) -> list[SdkMcpTool[Any]]:
    """The coach tools as in-process MCP tools for the Agent SDK.

    Each handler validates, runs and redacts through ``run_tool``. One lock
    serializes the calls: a single Stockfish process serves the coach.
    """
    lock = asyncio.Lock()

    def handler_for(name: str, source: str):
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            async with lock:
                emit({"type": "tool_start", "tool": name, "source": source})
                outcome = await asyncio.to_thread(run_tool, name, args, ctx)
                emit({"type": "tool_end", "tool": name, "source": source, "ok": outcome.ok})
            result: dict[str, Any] = {"content": [{"type": "text", "text": outcome.content}]}
            if not outcome.ok:
                result["is_error"] = True
            return result

        return handler

    return [
        SdkMcpTool(definition["name"], definition["description"], definition["input_schema"],
                   handler_for(definition["name"], TOOLS_BY_NAME[definition["name"]].source))
        for definition in tool_definitions()
    ]


class ClaudeProvider:
    """Claude through the local Claude Code login (subscription), via the Agent SDK.

    No API key is used: the SDK starts the bundled Claude Code CLI, which reads
    the login made with ``claude`` and ``/login``. Built-in tools, filesystem
    settings and other MCP servers are switched off, so the model sees only the
    coach tools below.
    """

    mode = "claude"

    def __init__(self, *, model: str = DEFAULT_MODEL, effort: str = "low", max_turns: int = 8) -> None:
        self.model = model
        self.effort = effort
        self.max_turns = max_turns

    def options(self, server: Any) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=self.model,
            effort=self.effort,
            system_prompt=SYSTEM_PROMPT,
            tools=[],
            setting_sources=[],
            mcp_servers={TOOL_SERVER: server},
            strict_mcp_config=True,
            allowed_tools=[TOOL_PREFIX + tool.name for tool in TOOLS],
            max_turns=self.max_turns,
            include_partial_messages=True,
            # .env is loaded into os.environ (chess_mcp.config), and the CLI would
            # bill a leftover API key instead of using the login: blank it.
            env={"ANTHROPIC_API_KEY": ""},
        )

    async def run(self, request: CoachRequest, ctx: ToolContext) -> AsyncIterator[Event]:
        yield {"type": "start", "mode": self.mode, "model": self.model}
        queue: asyncio.Queue[Any] = asyncio.Queue()
        server = create_sdk_mcp_server(TOOL_SERVER, tools=coach_tools(ctx, queue.put_nowait))

        async def pump() -> None:
            try:
                async for message in query(prompt=prompt_text(request, graph), options=self.options(server)):
                    queue.put_nowait(message)
            except Exception as exc:  # noqa: BLE001 - mapped to a safe message below
                queue.put_nowait(exc)
            finally:
                queue.put_nowait(_END)

        graph = None
        if request.played is None:
            # Ground the answer in the player's own record before Claude reads the question.
            queue.put_nowait({"type": "tool_start", "tool": "get_style_context", "source": "neo4j"})
            graph = await asyncio.to_thread(graph_context, request.fen, ctx)
            queue.put_nowait({"type": "tool_end", "tool": "get_style_context", "source": "neo4j", "ok": graph is not None})

        task = asyncio.create_task(pump())
        wrote = False  # text already sent in an earlier message of this answer
        new_message = False
        try:
            while (item := await queue.get()) is not _END:
                if isinstance(item, dict):
                    yield item
                elif isinstance(item, Exception):
                    yield {"type": "error", "message": sdk_error_message(item)}
                    return
                elif isinstance(item, StreamEvent):
                    kind = item.event.get("type")
                    delta = item.event.get("delta") or {}
                    if kind == "message_start":
                        new_message = wrote
                    elif kind == "content_block_delta" and delta.get("type") == "text_delta":
                        if new_message:
                            # Text before and after a tool round would otherwise run together.
                            yield {"type": "text", "text": "\n\n"}
                            new_message = False
                        wrote = True
                        yield {"type": "text", "text": delta["text"]}
                elif isinstance(item, ResultMessage):
                    if item.subtype == "error_max_turns":
                        yield {"type": "text", "text": MAX_TURNS_NOTE}
                    yield result_event(item, self.mode)
                    return
        finally:
            task.cancel()


def result_event(result: ResultMessage, mode: str) -> Event:
    """The last event of a Claude answer, from the SDK's result message."""
    if result.subtype == "error_max_turns":
        return {"type": "done", "mode": mode, "stop_reason": "max_turns"}
    if result.stop_reason == "refusal":
        return {"type": "error", "message": "Claude declined to answer this question."}
    if result.is_error or result.subtype != "success":
        detail = " ".join([result.result or "", *(result.errors or [])])
        if "login" in detail.casefold() or "logged in" in detail.casefold():
            return {"type": "error", "message": LOGIN_HINT}
        return {"type": "error", "message": f"Claude Code ended with an error ({result.subtype})."}
    return {"type": "done", "mode": mode, "stop_reason": result.stop_reason or "end_turn"}


def sdk_error_message(exc: Exception) -> str:
    """A user-facing message for an SDK failure. Never includes stderr or the prompt."""
    if isinstance(exc, CLINotFoundError):
        return "The Claude Code CLI was not found. Reinstall the project with uv sync."
    if isinstance(exc, ProcessError):
        detail = f"{exc} {exc.stderr or ''}".casefold()
        if "login" in detail or "logged in" in detail:
            return LOGIN_HINT
        return "Claude Code stopped with an error. Check that `claude -p hello` works in a terminal."
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
        # Two filtered reads: in an opening position the book moves alone can fill a limit.
        graph = yield from self._call("get_position_moves", {"fen": request.fen, "limit": 5, "by": "owner"}, ctx)
        book = yield from self._call("get_position_moves", {"fen": request.fen, "limit": 5, "by": "theory"}, ctx)
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
            yours = sorted(
                (m for m in graph.data.get("moves", []) if m.get("by") == "owner"),
                key=lambda m: m.get("games") or 0,
                reverse=True,
            )
            if yours:
                top = yours[0]
                loss = f", average loss {top['avg_cp_loss']} cp" if top.get("avg_cp_loss") is not None else ""
                lines.append(
                    f"Your games: you moved from here in {sum(m.get('games') or 0 for m in yours)} games; "
                    f"most often {top.get('san_move') or top['uci_move']} ({top.get('games')} games, {_record(top)}{loss})."
                )
            else:
                lines.append("Your games: you never had the move in this position in your stored games.")
            theory = [m.get("san_move") or m["uci_move"] for m in (book.data.get("moves", []) if book.ok else [])]
            if theory:
                lines.append("Theory here: " + ", ".join(theory) + ".")
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
