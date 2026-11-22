from types import SimpleNamespace

from chess_mcp import smoke
from chess_mcp.status import ServiceStatus, collect, render


def test_collect_reports_a_failing_service_without_raising() -> None:
    def broken() -> ServiceStatus:
        raise ConnectionError("password=secret")

    results = collect(
        {
            "postgres": lambda: ServiceStatus("postgres", True, "10 games"),
            "neo4j": broken,
        }
    )

    assert results[0].ok
    assert not results[1].ok
    # The exception message (which may hold connection details) is not shown.
    assert "secret" not in results[1].detail
    assert results[1].detail == "unreachable (ConnectionError)"


def test_render_marks_each_service() -> None:
    text = render(
        [ServiceStatus("postgres", True, "10 games"), ServiceStatus("neo4j", False, "down")]
    )
    assert text.splitlines() == ["[OK] postgres: 10 games", "[DOWN] neo4j: down"]


def test_smoke_contract_matches_the_server_tool_lists() -> None:
    from chess_mcp.neo4j.server import create_server as neo4j_server
    from chess_mcp.postgres.server import create_server as postgres_server
    from chess_mcp.stockfish.server import create_server as stockfish_server

    servers = {
        "postgres": postgres_server(object()),
        "neo4j": neo4j_server(object()),
        "stockfish": stockfish_server(object()),
    }
    for name, server in servers.items():
        registered = {tool.name for tool in server._tool_manager.list_tools()}
        assert registered == smoke.CHECKS[name].tools, name


def test_smoke_summaries_never_include_the_username() -> None:
    line = smoke.CHECKS["postgres"].summarise(
        {"username": "someone", "games_played": 12}
    )
    assert "someone" not in line
    assert "12 games" in line


def test_structured_falls_back_to_json_text() -> None:
    result = SimpleNamespace(
        structured_content=None,
        content=[SimpleNamespace(text='{"moves": [{"san": "e4"}]}')],
    )
    assert smoke._structured(result) == {"moves": [{"san": "e4"}]}


def test_smoke_rejects_unknown_server_names(capsys) -> None:
    assert smoke.main(["mysql"]) == 2
    assert "Unknown server" in capsys.readouterr().out
