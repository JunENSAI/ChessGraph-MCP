"""In-app coach: Claude via the Agent SDK (scripted fake query), offline mode, tools, route."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from claude_agent_sdk import CLINotFoundError, ProcessError, ResultMessage, StreamEvent
from fastapi.testclient import TestClient

import backend.coach.providers as providers
from backend.coach import ClaudeProvider, CoachRequest, OfflineProvider, ToolContext, provider_from_settings
from backend.coach.prompt import GRAPH_CONTEXT_HEADER, LINES_HEADER, PROFILE_HEADER, SYSTEM_PROMPT, prompt_text
from backend.coach.providers import format_score, sdk_error_message
from backend.coach.tools import (
    GRAPH_CONTEXT_CHARS,
    TOOLS,
    graph_context,
    rank_lines,
    read_style_context,
    redact,
    run_tool,
    style_profile,
    tool_definitions,
)
from chess_mcp.neo4j.models import StyleContext
from backend.main import create_app

OWNER = "OwnerAccount"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


# --------------------------------------------------------------------------- fakes


class FakePostgres:
    def get_player_summary(self, username: str, **_: Any) -> dict[str, Any]:
        return {"username": username, "games_played": 12, "wins": 6, "draws": 2, "losses": 4}

    def get_coaching_brief(self, player: str) -> dict[str, Any]:
        return {
            "strengths": [{"family": "London System", "games": 40, "wins": 25, "draws": 5, "losses": 10}],
            "target": {
                "family": "Sicilian Defense",
                "games": 20,
                "wins": 5,
                "draws": 3,
                "losses": 12,
                "splits": [
                    {
                        "fen": START,
                        "ply": 6,
                        "played_san": "a6",
                        "played_uci": "a7a6",
                        "best_uci": "e7e6",
                        "best_san": "e6",
                        "times": 4,
                        "average_cp_loss": 80,
                        "mate": False,
                    }
                ],
            },
            "calculation": [],
            "endgames": "Endgame type is not stored on games.",
            "tasks": [
                {"title": "Drill the Sicilian", "reason": "Weakest family: 5 wins in 20 games."},
                {"title": "Keep the London", "reason": "Best family."},
            ],
        }

    def get_blunders(self, *, player: str, game_id: int | None, minimum_cp_loss: int, limit: int):
        return [
            {
                "game_id": game_id,
                "white_username": OWNER,
                "black_username": "SomeOpponent",
                "move_number": 14,
                "san_move": "Qxb7",
                "uci_move": "d1b7",
                "fen_before_norm": START,
                "cp_loss": 350,
                "best_move_uci": "e2e4",
            }
        ]

    def list_games(self, **kwargs: Any):
        return [{"game_id": 1, "white_username": OWNER, "black_username": "SomeOpponent", "termination": f"{OWNER} won by checkmate"}]

    def close(self) -> None:
        return None


class FakeNeo4j:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.opening: str | None = "Queen's Pawn Game"
        self.nearby = 1

    def get_position_moves(self, fen: str, limit: int = 20, by: str = "all"):
        if self.fail:
            raise ConnectionError("bolt down")
        self.last_by = by
        moves = [
            {"relationship": "PLAYED_MOVE", "by": "opponent", "uci_move": "g1f3", "san_move": "Nf3", "games": 30, "wins": 10, "draws": 5, "losses": 15},
            {"relationship": "PLAYED_MOVE", "by": "owner", "uci_move": "e2e4", "san_move": "e4", "games": 9, "wins": 5, "draws": 2, "losses": 2, "avg_cp_loss": 12},
            {"relationship": "PLAYED_MOVE", "by": "owner", "uci_move": "c2c4", "san_move": "c4", "games": 2, "wins": 1, "draws": 0, "losses": 1},
            {"relationship": "THEORY_MOVE", "uci_move": "d2d4", "san_move": "d4"},
        ]
        if by == "theory":
            moves = [m for m in moves if m["relationship"] == "THEORY_MOVE"]
        elif by != "all":
            moves = [m for m in moves if m.get("by") == by]
        return {"fen_norm": fen, "moves": moves[:limit]}

    def get_style_context(self, fen: str, depth: int = 2, limit: int = 5) -> StyleContext:
        if self.fail:
            raise ConnectionError("bolt down")
        target = {"fen_norm": START}
        return StyleContext.model_validate(
            {
                "fen_norm": fen,
                "depth": depth,
                "position": {"fen_norm": fen, "phase": "opening", "eval_cp": 30, "best_move_san": "e4"},
                "opening": self.opening,
                "owner_moves": [
                    {"relationship": "PLAYED_MOVE", "by": "owner", "uci_move": "e2e4", "san_move": "e4", "games": 9,
                     "wins": 5, "draws": 2, "losses": 2, "avg_cp_loss": 12, "target": target}
                ],
                "theory_moves": [{"relationship": "THEORY_MOVE", "uci_move": "d2d4", "san_move": "d4", "target": target}],
                "total_games": 11,
                "owner_wins": 6,
                "nearby_mistakes": [
                    {"position": {"fen_norm": f"{START} {i}"}, "distance": 1, "games": 3, "average_cp_loss": 140.4,
                     "played_moves": ["c4"], "best_moves": ["d2d4"]}
                    for i in range(self.nearby)
                ],
            }
        )

    def get_theory_exits(self, limit: int = 20, by: str = "owner"):
        return {"by": by, "exits": [{"played_uci": "c2c4", "games": 3, "limit": limit}]}

    def close(self) -> None:
        return None


def _line(san: list[str], uci: list[str], value: int = 35) -> dict[str, Any]:
    return {"move_uci": uci[0], "move_san": san[0], "score": {"type": "cp", "value": value}, "pv": {"uci": uci, "san": san}}


class FakeStockfish:
    fail = False

    def analyze_position(self, fen: str, *, limit_type: str, limit_value: int | None, multipv: int):
        if self.fail:
            raise RuntimeError("engine down")
        return {
            "fen": fen,
            "root_player": "white",
            "limit": {"type": "depth", "value": limit_value or 6, "unit": "plies"},
            "multipv": multipv,
            "lines": [
                _line(["e4", "e5", "Nf3"], ["e2e4", "e7e5", "g1f3"]),
                _line(["d4", "d5", "c4"], ["d2d4", "d7d5", "c2c4"], 30),
                _line(["Nf3", "Nf6", "g3"], ["g1f3", "g8f6", "g2g3"], 20),
            ][:multipv],
        }

    def compare_move(self, fen: str, played: str, *, limit_type: str, limit_value: int | None):
        return {
            "root_player": "white",
            "played_move_san": "Qxb7",
            "limit": {"type": "depth", "value": 6, "unit": "plies"},
            "best": _line(["e4"], ["e2e4"], 40),
            "played": _line(["Qxb7"], ["d1b7"], -310),
            "centipawn_loss": 350,
        }

    def validate_line(self, fen: str, moves: list[str]):
        return {"moves": [{"san": "e4"}]}

    def close(self) -> None:
        return None


def make_ctx(neo4j_fail: bool = False) -> ToolContext:
    pg, graph, sf = FakePostgres(), FakeNeo4j(neo4j_fail), FakeStockfish()
    return ToolContext(postgres=lambda: pg, neo4j=lambda: graph, stockfish=lambda: sf, player=OWNER)


def fake_server(name: str, version: str = "1.0.0", tools: list[Any] | None = None) -> dict[str, Any]:
    """Stands in for create_sdk_mcp_server so a scripted query can call the handlers."""
    return {"type": "sdk", "name": name, "tools": {tool.name: tool for tool in tools or []}}


def script(monkeypatch, steps: list[Any]) -> list[dict[str, Any]]:
    """Replace the SDK query with a script.

    A step is an SDK message to yield, an exception to raise, or
    ``("tool", name, args)`` to call that coach tool the way Claude Code would.
    """
    calls: list[dict[str, Any]] = []

    async def fake_query(*, prompt: str, options: Any):
        calls.append({"prompt": prompt, "options": options})
        tools = options.mcp_servers["coach"]["tools"]
        for step in steps:
            if isinstance(step, Exception):
                raise step
            if isinstance(step, tuple):
                _, name, args = step
                calls.append({"tool": name, "result": await tools[name].handler(args)})
                continue
            yield step

    monkeypatch.setattr(providers, "create_sdk_mcp_server", fake_server)
    monkeypatch.setattr(providers, "query", fake_query)
    return calls


def delta(text: str) -> StreamEvent:
    event = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}
    return StreamEvent(uuid="u", session_id="s", event=event)


def result(subtype: str = "success", *, is_error: bool = False, stop_reason: str | None = "end_turn", text: str | None = None) -> ResultMessage:
    return ResultMessage(
        subtype=subtype, duration_ms=1, duration_api_ms=1, is_error=is_error, num_turns=1,
        session_id="s", stop_reason=stop_reason, result=text,
    )


def collect(provider: Any, req: CoachRequest, ctx: ToolContext) -> list[dict[str, Any]]:
    async def run() -> list[dict[str, Any]]:
        return [event async for event in provider.run(req, ctx)]

    return asyncio.run(run())


def request(**overrides: Any) -> CoachRequest:
    return CoachRequest(**{"question": "What should I play?", "fen": START, **overrides})


# --------------------------------------------------------------------------- Claude (Agent SDK)


PREFETCH = [
    {"type": "tool_start", "tool": "get_player_profile", "source": "postgres"},
    {"type": "tool_end", "tool": "get_player_profile", "source": "postgres", "ok": True},
    {"type": "tool_start", "tool": "get_style_context", "source": "neo4j"},
    {"type": "tool_end", "tool": "get_style_context", "source": "neo4j", "ok": True},
    {"type": "tool_start", "tool": "analyze_position", "source": "stockfish"},
    {"type": "tool_end", "tool": "analyze_position", "source": "stockfish", "ok": True},
]


def block(prompt: str, header: str) -> Any:
    return json.loads(prompt.split(header + "\n", 1)[1].split("\n", 1)[0])


def test_claude_streams_text_and_reports_each_tool_call(monkeypatch) -> None:
    calls = script(
        monkeypatch,
        [
            delta("Checking. "),
            ("tool", "get_player_summary", {}),
            ("tool", "analyze_position", {"fen": START}),
            delta("EVAL +0.35. MOVE: e4\nPLAY: e2e4 e7e5"),
            result(),
        ],
    )
    events = collect(ClaudeProvider(), request(), make_ctx())

    kinds = [event["type"] for event in events]
    assert kinds[8:] == ["text", "tool_start", "tool_end", "tool_start", "tool_end", "text", "done"]
    assert events[0] == {"type": "start", "mode": "claude", "model": "claude-opus-5-5"}
    assert events[1:7] == PREFETCH
    assert events[7]["type"] == "lines"
    assert events[9] == {"type": "tool_start", "tool": "get_player_summary", "source": "postgres"}
    assert events[11]["source"] == "stockfish"
    assert all(event["ok"] for event in events if event["type"] == "tool_end")
    assert events[-1] == {"type": "done", "mode": "claude", "stop_reason": "end_turn"}

    summary = calls[1]["result"]
    assert "is_error" not in summary
    # The account name never reaches Claude.
    assert OWNER.casefold() not in json.dumps([c.get("result") for c in calls[1:]]).casefold()
    assert json.loads(summary["content"][0]["text"])["username"] == "you"


def test_claude_options_isolate_the_session_to_the_coach_tools(monkeypatch) -> None:
    calls = script(monkeypatch, [result()])
    collect(ClaudeProvider(model="claude-opus-5-5", effort="low"), request(), make_ctx())

    options = calls[0]["options"]
    assert options.model == "claude-opus-5-5"
    assert options.effort == "low"
    assert options.system_prompt == SYSTEM_PROMPT
    assert options.tools == []  # no built-in tools (Bash, Read, ...)
    assert options.setting_sources == []  # no user/project settings, hooks or CLAUDE.md
    assert options.strict_mcp_config is True
    assert options.include_partial_messages is True
    # A leftover key loaded from .env must not switch the CLI to API billing.
    assert options.env == {"ANTHROPIC_API_KEY": ""}
    assert options.allowed_tools == [f"mcp__coach__{tool.name}" for tool in TOOLS]
    assert set(options.mcp_servers["coach"]["tools"]) == {tool.name for tool in TOOLS}
    assert calls[0]["prompt"].startswith(f"Current position (FEN): {START}")


def test_invalid_tool_input_returns_an_error_result_to_claude(monkeypatch) -> None:
    calls = script(monkeypatch, [("tool", "analyze_position", {"multipv": 9}), result()])
    events = collect(ClaudeProvider(), request(), make_ctx())

    assert [e["ok"] for e in events if e["type"] == "tool_end"] == [True, True, True, False]
    tool_result = calls[1]["result"]
    assert tool_result["is_error"] is True
    assert "fen" in tool_result["content"][0]["text"]


def test_a_down_store_becomes_an_error_result_not_a_crash(monkeypatch) -> None:
    calls = script(monkeypatch, [("tool", "get_position_moves", {"fen": START}), result()])
    events = collect(ClaudeProvider(), request(), make_ctx(neo4j_fail=True))
    assert calls[1]["result"]["is_error"] is True
    assert "neo4j is unavailable" in calls[1]["result"]["content"][0]["text"]
    assert events[-1]["type"] == "done"


def test_turn_cap_ends_the_answer_with_a_notice(monkeypatch) -> None:
    script(monkeypatch, [delta("Checking."), result("error_max_turns", is_error=True, stop_reason=None)])
    events = collect(ClaudeProvider(), request(), make_ctx())
    assert events[-2] == {"type": "text", "text": providers.MAX_TURNS_NOTE}
    assert events[-1] == {"type": "done", "mode": "claude", "stop_reason": "max_turns"}


def message_start() -> StreamEvent:
    return StreamEvent(uuid="u", session_id="s", event={"type": "message_start", "message": {}})


def test_text_of_separate_messages_is_kept_apart(monkeypatch) -> None:
    script(
        monkeypatch,
        [message_start(), delta("Checking."), ("tool", "get_player_summary", {}), message_start(), delta("MOVE: e4"), result()],
    )
    events = collect(ClaudeProvider(), request(), make_ctx())
    text = "".join(event["text"] for event in events if event["type"] == "text")
    assert text == "Checking.\n\nMOVE: e4"


def test_refusal_ends_with_an_error_event(monkeypatch) -> None:
    script(monkeypatch, [result(stop_reason="refusal")])
    events = collect(ClaudeProvider(), request(), make_ctx())
    assert events[-1]["type"] == "error"
    assert "declined" in events[-1]["message"]


def test_a_missing_login_asks_for_claude_login(monkeypatch) -> None:
    script(monkeypatch, [result(is_error=True, text="Not logged in · Please run /login")])
    events = collect(ClaudeProvider(), request(), make_ctx())
    assert events[-1] == {"type": "error", "message": providers.LOGIN_HINT}


def test_sdk_errors_map_to_safe_messages(monkeypatch) -> None:
    script(monkeypatch, [CLINotFoundError()])
    events = collect(ClaudeProvider(), request(), make_ctx())
    assert events[-1]["type"] == "error"
    assert "CLI was not found" in events[-1]["message"]

    secret = ProcessError("Command failed", exit_code=1, stderr="prompt with private text")
    assert "private" not in sdk_error_message(secret)
    assert sdk_error_message(ProcessError("x", stderr="Not logged in")) == providers.LOGIN_HINT
    assert sdk_error_message(RuntimeError("x")) == "The coach failed (RuntimeError)."


def test_evidence_is_fetched_in_order_and_put_in_the_prompt(monkeypatch) -> None:
    calls = script(monkeypatch, [result()])
    events = collect(ClaudeProvider(), request(), make_ctx())

    # Games, then graph, then Stockfish (the CLAUDE.md evidence order), then the lines for the board.
    assert events[1:7] == PREFETCH
    lines_event = events[7]
    assert lines_event["type"] == "lines"
    assert lines_event["root_player"] == "white" and lines_event["depth"] == 6
    assert [line["uci"][0] for line in lines_event["lines"]] == ["e2e4", "d2d4", "g1f3"]
    assert [line["human"] for line in lines_event["lines"]] == [True, False, False]  # e4: 9 of your games

    prompt = calls[0]["prompt"]
    profile = block(prompt, PROFILE_HEADER)
    assert profile["record"]["games_played"] == 12
    assert profile["weakest_opening"]["family"] == "Sicilian Defense"
    assert profile["repeated_mistake"] == {"ply": 6, "played_san": "a6", "best_san": "e6", "times": 4, "average_cp_loss": 80}
    graph = block(prompt, GRAPH_CONTEXT_HEADER)
    assert graph["your_moves"][0] == {"move": "e4", "uci": "e2e4", "games": 9, "wins": 5, "draws": 2, "losses": 2, "avg_cp_loss": 12}
    assert graph["book_moves"] == ["d4"]
    assert graph["your_games_here"] == {"games": 11, "wins": 6, "draws": 0, "losses": 0}
    lines = block(prompt, LINES_HEADER)
    assert lines["lines"][0] == {"rank": 1, "san": ["e4", "e5", "Nf3"], "score": {"type": "cp", "value": 35}, "games": 9, "book": False, "human": True}
    assert lines["lines"][1]["book"] is True
    assert prompt.index(PROFILE_HEADER) < prompt.index(GRAPH_CONTEXT_HEADER) < prompt.index(LINES_HEADER)
    assert prompt.endswith("What should I play?")
    assert OWNER.casefold() not in prompt.casefold()


def test_graph_context_is_skipped_when_neo4j_is_down(monkeypatch) -> None:
    calls = script(monkeypatch, [result()])
    events = collect(ClaudeProvider(), request(), make_ctx(neo4j_fail=True))
    assert events[4] == {"type": "tool_end", "tool": "get_style_context", "source": "neo4j", "ok": False}
    assert GRAPH_CONTEXT_HEADER not in calls[0]["prompt"]
    # The lines still come, with no human tag from the graph.
    lines = next(e for e in events if e["type"] == "lines")
    assert not any(line["human"] for line in lines["lines"])


def test_lines_are_skipped_when_stockfish_fails(monkeypatch) -> None:
    calls = script(monkeypatch, [result()])
    ctx = make_ctx()
    ctx.stockfish().fail = True
    events = collect(ClaudeProvider(), request(), ctx)
    assert events[6] == {"type": "tool_end", "tool": "analyze_position", "source": "stockfish", "ok": False}
    assert not [e for e in events if e["type"] == "lines"]
    assert LINES_HEADER not in calls[0]["prompt"]


def test_the_profile_is_read_once_per_ten_minutes(monkeypatch) -> None:
    script(monkeypatch, [result()])
    ctx = make_ctx()
    reads = []
    real = ctx.postgres().get_coaching_brief
    monkeypatch.setattr(ctx.postgres(), "get_coaching_brief", lambda player: reads.append(player) or real(player))
    provider = ClaudeProvider()
    collect(provider, request(), ctx)
    collect(provider, request(), ctx)
    assert len(reads) == 1
    monkeypatch.setattr(providers.time, "monotonic", lambda: 10_000_000.0)
    collect(provider, request(), ctx)
    assert len(reads) == 2


def test_a_played_move_explanation_skips_the_evidence(monkeypatch) -> None:
    calls = script(monkeypatch, [result()])
    played = {"san": "Nf6", "color": "black", "eval_text": "+0.20"}
    events = collect(ClaudeProvider(), request(played=played), make_ctx())
    assert not [e for e in events if e["type"] in ("tool_start", "lines")]
    assert PROFILE_HEADER not in calls[0]["prompt"] and GRAPH_CONTEXT_HEADER not in calls[0]["prompt"]


def test_graph_context_is_redacted_and_bounded() -> None:
    ctx = make_ctx()
    graph = ctx.neo4j()
    graph.opening = f"{OWNER} Gambit"
    graph.nearby = 200
    text = graph_context(read_style_context(START, ctx), ctx)
    assert text is not None
    assert len(text) <= GRAPH_CONTEXT_CHARS
    assert OWNER.casefold() not in text.casefold()
    data = json.loads(text)
    assert data["opening"] == "you Gambit"
    assert 0 < len(data["nearby_mistakes"]) < 200  # trimmed from the end
    assert data["your_moves"]  # never trimmed
    assert graph_context(None, ctx) is None


def _analysis(*first_moves: str) -> dict[str, Any]:
    return {
        "root_player": "black",
        "limit": {"value": 12},
        "lines": [{"score": {"type": "cp", "value": 10 - i}, "pv": {"uci": [m, "a2a3"], "san": [m, "a3"]}} for i, m in enumerate(first_moves)],
    }


def test_rank_lines_tags_the_most_played_then_book_then_none() -> None:
    analysis = _analysis("e7e5", "c7c5", "e7e6")
    played = rank_lines(analysis, {"c7c5": 40, "e7e6": 3}, {"e7e5"})
    assert [line["human"] for line in played["lines"]] == [False, True, False]
    assert played["depth"] == 12 and played["root_player"] == "black"
    booked = rank_lines(analysis, {}, {"e7e6", "c7c5"})
    assert [line["human"] for line in booked["lines"]] == [False, True, False]  # best-ranked book line
    assert not any(line["human"] for line in rank_lines(analysis, {}, set())["lines"])
    assert rank_lines({"lines": []}, {}, set()) is None


def test_style_profile_is_none_when_postgres_fails(monkeypatch) -> None:
    ctx = make_ctx()

    def down(player: str):
        raise ConnectionError("pg down")

    monkeypatch.setattr(ctx.postgres(), "get_coaching_brief", down)
    assert style_profile(ctx) is None


# --------------------------------------------------------------------------- offline


def test_offline_position_answer_uses_engine_and_graph() -> None:
    events = list(OfflineProvider().run(request(), make_ctx()))
    tools = [e["tool"] for e in events if e["type"] == "tool_start"]
    assert tools == ["get_position_moves", "get_position_moves", "analyze_position"]
    lines = next(e for e in events if e["type"] == "lines")
    assert [line["human"] for line in lines["lines"]] == [True, False, False]
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "Position: +0.35 for White (side to move), Stockfish depth 6." in text
    assert "1. e4 e5 Nf3 (+0.35 for White (side to move)) · human (9 of your games)" in text
    assert "2. d4 d5 c4 (+0.30 for White (side to move))" in text
    # Only the owner's moves count as "your games"; the opponent's 30 games of Nf3 do not.
    assert "you moved from here in 11 games; most often e4 (9 games, 5W 2D 2L, average loss 12 cp)" in text
    assert "Theory here: d4." in text
    assert "Offline evidence mode" in text
    assert "PLAY:" not in text  # the board draws the lines event
    assert events[0] == {"type": "start", "mode": "offline", "model": None}
    assert events[-1]["type"] == "done"


def test_offline_says_graph_evidence_is_missing_when_neo4j_is_down() -> None:
    events = list(OfflineProvider().run(request(), make_ctx(neo4j_fail=True)))
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "graph evidence is missing" in text
    assert "1. e4 e5 Nf3" in text


def test_offline_training_question_reads_the_coaching_brief() -> None:
    events = list(OfflineProvider().run(request(question="What should I train?"), make_ctx()))
    assert [e["tool"] for e in events if e["type"] == "tool_start"] == ["get_coaching_brief"]
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "STRENGTH: London System, 40 games, 25W 5D 10L." in text
    assert "TARGET: Sicilian Defense" in text
    assert "You played a6 at ply 6 4 times; the stored engine move is e6" in text
    assert "1. Drill the Sicilian: Weakest family" in text
    assert "PLAY:" not in text


def test_offline_game_question_reviews_the_largest_mistake() -> None:
    events = list(OfflineProvider().run(request(question="Why did I lose?", game_id=7, view="review"), make_ctx()))
    assert [e["tool"] for e in events if e["type"] == "tool_start"] == ["get_blunders", "compare_move"]
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "Move 14 Qxb7: 350 cp lost" in text
    assert "Stockfish prefers e4 (+0.40 for White (side to move)) over Qxb7" in text


def test_offline_played_move_explanation_calls_no_tool() -> None:
    played = {"san": "Nf6", "color": "black", "eval_text": "+0.20"}
    events = list(OfflineProvider().run(request(played=played), make_ctx()))
    assert not [e for e in events if e["type"] == "tool_start"]
    assert "Stockfish played Nf6 for black" in "".join(e.get("text", "") for e in events)


def test_mate_sized_losses_are_described_as_mate_swings() -> None:
    from backend.coach.providers import describe_loss

    assert describe_loss(350) == "350 cp lost"
    assert describe_loss(9538).startswith("a mate swing")


def test_format_score_handles_mate_both_ways() -> None:
    assert format_score({"type": "mate", "value": 3}, "white") == "mate in 3 for White"
    assert format_score({"type": "mate", "value": -2}, "black") == "Black is mated in 2"


# --------------------------------------------------------------------------- tools and prompt


def test_redact_replaces_owner_and_opponents_everywhere() -> None:
    data = {
        "white_username": OWNER.upper(),
        "black_username": "Rival",
        "termination": f"Rival won on time against {OWNER}",
        "nested": [{"username": OWNER}],
    }
    cleaned = redact(data, OWNER)
    assert cleaned["white_username"] == "you"
    assert cleaned["black_username"] == "opponent"
    assert cleaned["termination"] == "opponent won on time against you"
    assert cleaned["nested"][0]["username"] == "you"


def test_list_games_result_is_redacted() -> None:
    outcome = run_tool("list_games", {"limit": 1}, make_ctx())
    assert outcome.ok
    assert OWNER not in outcome.content
    assert "SomeOpponent" not in outcome.content


def test_unknown_tool_and_extra_arguments_are_rejected() -> None:
    assert not run_tool("drop_table", {}, make_ctx()).ok
    rejected = run_tool("get_player_summary", {"username": "someone"}, make_ctx())
    assert not rejected.ok
    assert "username" in rejected.content


def test_tool_definitions_are_closed_and_untitled() -> None:
    definitions = tool_definitions()
    assert len({d["name"] for d in definitions}) == len(definitions) == 14
    for definition in definitions:
        schema = definition["input_schema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert "title" not in schema
        assert all("title" not in prop for prop in schema["properties"].values())
    assert tool_definitions() == definitions  # stable for prompt caching


def test_prompt_text_puts_earlier_turns_before_the_board_context() -> None:
    req = request(
        history=[
            {"role": "coach", "text": "Welcome."},
            {"role": "user", "text": "Hi"},
        ],
        summary="Move 12, after Nf3",
        profile="Weakest: Sicilian",
    )
    text = prompt_text(req)
    assert text.startswith("Earlier in this conversation:\nCoach: Welcome.\n\nMe: Hi")
    last = text.split("---\n\n", 1)[1]
    assert last.startswith(f"Current position (FEN): {START}")
    assert "My profile: Weakest: Sicilian" in last
    assert last.endswith("What should I play?")
    assert prompt_text(request()).startswith("Current position (FEN):")


# --------------------------------------------------------------------------- route and settings


def _app(coach: Any) -> TestClient:
    return TestClient(create_app(postgres=FakePostgres(), neo4j=FakeNeo4j(), stockfish=FakeStockfish(), coach=coach))


def _sse(response) -> list[dict[str, Any]]:
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_chat_route_streams_server_sent_events(monkeypatch) -> None:
    monkeypatch.setenv("CHESS_USERNAME", OWNER)
    with _app(OfflineProvider()) as client:
        response = client.post("/api/coach/chat", json={"question": "Best move?", "fen": START})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _sse(response)
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "done"
        assert client.get("/api/coach/status").json() == {"mode": "offline", "model": None}


def test_chat_route_validates_the_body(monkeypatch) -> None:
    monkeypatch.setenv("CHESS_USERNAME", OWNER)
    with _app(OfflineProvider()) as client:
        assert client.post("/api/coach/chat", json={"question": "", "fen": START}).status_code == 422


def _settings(monkeypatch, **values: str) -> None:
    monkeypatch.setattr("backend.coach.get_setting", lambda name, default="": values.get(name, default))


def test_provider_defaults_to_claude_opus_at_low_effort(monkeypatch) -> None:
    _settings(monkeypatch, CLAUDE_EFFORT="bogus")
    provider = provider_from_settings()
    assert provider.mode == "claude"
    assert provider.model == "claude-opus-5-5"
    assert provider.effort == "low"


def test_coach_mode_offline_selects_the_template(monkeypatch) -> None:
    _settings(monkeypatch, COACH_MODE="offline")
    assert provider_from_settings().mode == "offline"


def test_chat_route_streams_an_async_provider(monkeypatch) -> None:
    monkeypatch.setenv("CHESS_USERNAME", OWNER)
    script(monkeypatch, [delta("MOVE: e4"), result()])
    with _app(ClaudeProvider()) as client:
        events = _sse(client.post("/api/coach/chat", json={"question": "Best move?", "fen": START}))
    assert [e["type"] for e in events] == ["start", *["tool_start", "tool_end"] * 3, "lines", "text", "done"]


@pytest.mark.parametrize("question", ["what should I train", "my weakness", "Make a training plan for me", "my mistakes"])
def test_course_questions_are_detected(question: str) -> None:
    from backend.coach.providers import COURSE_QUESTION

    assert COURSE_QUESTION.search(question)


@pytest.mark.parametrize("question", ["What should I play?", "Who is better here?", "What is the plan in this position?"])
def test_position_questions_are_not_course_questions(question: str) -> None:
    from backend.coach.providers import COURSE_QUESTION

    assert not COURSE_QUESTION.search(question)


def test_graph_tools_pass_the_mover_filter_and_reject_unknown_values() -> None:
    ctx = make_ctx()
    assert run_tool("get_position_moves", {"fen": START, "by": "owner"}, ctx).ok
    assert ctx.neo4j().last_by == "owner"
    assert not run_tool("get_position_moves", {"fen": START, "by": "everyone"}, ctx).ok

    exits = run_tool("get_theory_exits", {}, ctx)
    assert exits.ok
    assert exits.data == {"by": "owner", "exits": [{"played_uci": "c2c4", "games": 3, "limit": 10}]}
    assert not run_tool("get_theory_exits", {"limit": 50}, ctx).ok


def test_offline_position_answer_without_owner_moves_still_lists_theory() -> None:
    class NoOwnerMoves(FakeNeo4j):
        def get_position_moves(self, fen: str, limit: int = 20, by: str = "all"):
            result = super().get_position_moves(fen, limit, by)
            result["moves"] = [m for m in result["moves"] if m.get("by") != "owner"]
            return result

    pg, graph, sf = FakePostgres(), NoOwnerMoves(), FakeStockfish()
    ctx = ToolContext(postgres=lambda: pg, neo4j=lambda: graph, stockfish=lambda: sf, player=OWNER)
    text = "".join(e["text"] for e in OfflineProvider().run(request(), ctx) if e["type"] == "text")
    assert "you never had the move in this position" in text
    assert "Theory here: d4." in text
