"""In-app coach: the Claude tool loop (scripted fake client), offline mode, tools, route."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from backend.coach import ClaudeProvider, CoachRequest, OfflineProvider, ToolContext, provider_from_settings
from backend.coach.prompt import SYSTEM_PROMPT, conversation
from backend.coach.providers import FALLBACK_BETA, api_error_message, format_score
from backend.coach.tools import TOOLS, redact, run_tool, tool_definitions
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

    def get_theory_exits(self, limit: int = 20, by: str = "owner"):
        return {"by": by, "exits": [{"played_uci": "c2c4", "games": 3, "limit": limit}]}

    def close(self) -> None:
        return None


def _line(san: list[str], uci: list[str], value: int = 35) -> dict[str, Any]:
    return {"move_uci": uci[0], "move_san": san[0], "score": {"type": "cp", "value": value}, "pv": {"uci": uci, "san": san}}


class FakeStockfish:
    def analyze_position(self, fen: str, *, limit_type: str, limit_value: int | None, multipv: int):
        return {
            "fen": fen,
            "root_player": "white",
            "limit": {"type": "depth", "value": limit_value or 6, "unit": "plies"},
            "multipv": multipv,
            "lines": [_line(["e4", "e5", "Nf3"], ["e2e4", "e7e5", "g1f3"])],
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


def text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def tool_block(block_id: str, name: str, args: dict[str, Any]):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=args)


class FakeStream:
    def __init__(self, message: Any) -> None:
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def __iter__(self):
        for block in self.message.content:
            if block.type == "text":
                yield SimpleNamespace(type="text", text=block.text)

    def get_final_message(self):
        return self.message


class FakeMessages:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def stream(self, **params: Any) -> FakeStream:
        # Snapshot the messages: the provider keeps appending to the same list.
        self.calls.append({**params, "messages": list(params["messages"])})
        if not self.script:
            raise AssertionError("unexpected extra API call")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeStream(item)


class FakeClient:
    def __init__(self, script: list[Any]) -> None:
        self.messages = FakeMessages(script)
        self.beta = SimpleNamespace(messages=self.messages)


def message(stop_reason: str, *blocks: Any):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def request(**overrides: Any) -> CoachRequest:
    return CoachRequest(**{"question": "What should I play?", "fen": START, **overrides})


# --------------------------------------------------------------------------- Claude loop


def test_claude_loop_runs_parallel_tools_and_returns_results_in_one_message() -> None:
    client = FakeClient(
        [
            message(
                "tool_use",
                text_block("Checking. "),
                tool_block("t1", "get_player_summary", {}),
                tool_block("t2", "analyze_position", {"fen": START}),
            ),
            message("end_turn", text_block("EVAL +0.35. MOVE: e4\nPLAY: e2e4 e7e5")),
        ]
    )
    provider = ClaudeProvider(client, refusal_fallback=False)

    events = list(provider.run(request(), make_ctx()))

    kinds = [event["type"] for event in events]
    assert kinds == ["start", "text", "tool_start", "tool_end", "tool_start", "tool_end", "text", "done"]
    assert events[2] == {"type": "tool_start", "tool": "get_player_summary", "source": "postgres"}
    assert events[4]["source"] == "stockfish"
    assert all(event["ok"] for event in events if event["type"] == "tool_end")

    second = client.messages.calls[1]["messages"]
    assert second[-2]["role"] == "assistant"
    results = second[-1]["content"]
    assert [result["tool_use_id"] for result in results] == ["t1", "t2"]
    assert not any(result.get("is_error") for result in results)
    # The account name never reaches the API.
    assert OWNER.casefold() not in json.dumps(second, default=str).casefold()
    assert json.loads(results[0]["content"])["username"] == "you"


def test_claude_request_parameters() -> None:
    client = FakeClient([message("end_turn", text_block("Done."))])
    list(ClaudeProvider(client, model="claude-opus-5-5", effort="low").run(request(), make_ctx()))

    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["system"] == SYSTEM_PROMPT
    assert call["output_config"] == {"effort": "low"}
    assert call["cache_control"] == {"type": "ephemeral"}
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"
    assert [tool["name"] for tool in call["tools"]] == [tool.name for tool in TOOLS]
    assert call["messages"][0]["role"] == "user"


def test_claude_without_fallback_uses_the_plain_endpoint() -> None:
    client = FakeClient([message("end_turn", text_block("Done."))])
    list(ClaudeProvider(client, refusal_fallback=False).run(request(), make_ctx()))
    assert "betas" not in client.messages.calls[0]
    assert "fallbacks" not in client.messages.calls[0]


def test_invalid_tool_input_returns_an_error_result_to_claude() -> None:
    client = FakeClient(
        [
            message("tool_use", tool_block("t1", "analyze_position", {"multipv": 9})),
            message("end_turn", text_block("Evidence is missing.")),
        ]
    )
    events = list(ClaudeProvider(client, refusal_fallback=False).run(request(), make_ctx()))

    assert [e["ok"] for e in events if e["type"] == "tool_end"] == [False]
    result = client.messages.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "fen" in result["content"]


def test_a_down_store_becomes_an_error_result_not_a_crash() -> None:
    client = FakeClient(
        [
            message("tool_use", tool_block("t1", "get_position_moves", {"fen": START})),
            message("end_turn", text_block("Graph evidence is missing.")),
        ]
    )
    events = list(ClaudeProvider(client, refusal_fallback=False).run(request(), make_ctx(neo4j_fail=True)))
    result = client.messages.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "neo4j is unavailable" in result["content"]
    assert events[-1]["type"] == "done"


def test_iteration_cap_stops_the_loop() -> None:
    looping = [message("tool_use", tool_block(f"t{i}", "get_player_summary", {})) for i in range(3)]
    client = FakeClient(looping)
    events = list(ClaudeProvider(client, refusal_fallback=False, max_iterations=2).run(request(), make_ctx()))
    assert len(client.messages.calls) == 2
    assert events[-1] == {"type": "done", "mode": "claude", "stop_reason": "max_iterations"}


def test_refusal_ends_with_an_error_event() -> None:
    client = FakeClient([message("refusal")])
    events = list(ClaudeProvider(client).run(request(), make_ctx()))
    assert events[-1]["type"] == "error"
    assert "declined" in events[-1]["message"]


def test_pause_turn_is_resent() -> None:
    client = FakeClient([message("pause_turn", text_block("…")), message("end_turn", text_block("Done."))])
    events = list(ClaudeProvider(client, refusal_fallback=False).run(request(), make_ctx()))
    assert len(client.messages.calls) == 2
    assert events[-1]["type"] == "done"


def test_api_errors_map_to_safe_messages() -> None:
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    auth = anthropic.AuthenticationError("bad key sk-ant-secret", response=httpx2.Response(401, request=req), body=None)
    client = FakeClient([auth])
    events = list(ClaudeProvider(client).run(request(), make_ctx()))
    assert events[-1]["type"] == "error"
    assert "ANTHROPIC_API_KEY" in events[-1]["message"]
    assert "sk-ant" not in events[-1]["message"]
    assert "reach" in api_error_message(anthropic.APIConnectionError(request=req))
    assert api_error_message(RuntimeError("x")) == "The coach failed (RuntimeError)."


# --------------------------------------------------------------------------- offline


def test_offline_position_answer_uses_engine_and_graph() -> None:
    events = list(OfflineProvider().run(request(), make_ctx()))
    tools = [e["tool"] for e in events if e["type"] == "tool_start"]
    assert tools == ["analyze_position", "get_position_moves", "get_position_moves"]
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "EVAL: +0.35 for White (side to move), Stockfish depth 6." in text
    assert "MOVE: e4" in text
    # Only the owner's moves count as "your games"; the opponent's 30 games of Nf3 do not.
    assert "you moved from here in 11 games; most often e4 (9 games, 5W 2D 2L, average loss 12 cp)" in text
    assert "Theory here: d4." in text
    assert "Offline evidence mode" in text
    assert text.rstrip().endswith("PLAY: e2e4 e7e5 g1f3")
    assert events[0] == {"type": "start", "mode": "offline", "model": None}
    assert events[-1]["type"] == "done"


def test_offline_says_graph_evidence_is_missing_when_neo4j_is_down() -> None:
    events = list(OfflineProvider().run(request(), make_ctx(neo4j_fail=True)))
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "Graph evidence is missing" in text
    assert "MOVE: e4" in text


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


def test_conversation_starts_with_user_and_ends_with_the_board_context() -> None:
    req = request(
        history=[
            {"role": "coach", "text": "Welcome."},
            {"role": "user", "text": "Hi"},
            {"role": "coach", "text": "Hello."},
        ],
        summary="Move 12, after Nf3",
        profile="Weakest: Sicilian",
    )
    messages = conversation(req)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    last = messages[-1]["content"]
    assert last.startswith(f"Current position (FEN): {START}")
    assert "My profile: Weakest: Sicilian" in last
    assert last.endswith("What should I play?")


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


def test_provider_is_offline_without_a_key(monkeypatch) -> None:
    _settings(monkeypatch)
    assert provider_from_settings().mode == "offline"


def test_provider_is_claude_with_a_key(monkeypatch) -> None:
    _settings(monkeypatch, ANTHROPIC_API_KEY="sk-ant-test", CLAUDE_EFFORT="bogus", CLAUDE_REFUSAL_FALLBACK="off")
    provider = provider_from_settings()
    assert provider.mode == "claude"
    assert provider.model == "claude-opus-5-5"
    assert provider.effort == "low"
    assert provider.refusal_fallback is False


def test_coach_mode_offline_overrides_a_key(monkeypatch) -> None:
    _settings(monkeypatch, ANTHROPIC_API_KEY="sk-ant-test", COACH_MODE="offline")
    assert provider_from_settings().mode == "offline"


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
