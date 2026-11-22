"""Health report for the three ChessGraph evidence stores.

    uv run chessgraph-status

Prints one line per service with row or node counts. Every check is a
read; nothing personal (such as the account name) is printed. The Claude Code
plugin's ``/chessgraph:status`` skill runs this command.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass

CHESS_LABELS = ("Position", "Game", "Opening", "EndgamePattern")


@dataclass(frozen=True)
class ServiceStatus:
    service: str
    ok: bool
    detail: str


def check_postgres() -> ServiceStatus:
    from sqlalchemy import create_engine, text

    from chess_mcp.config import postgres_url

    engine = create_engine(postgres_url())
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            games = conn.execute(text("SELECT count(*) FROM games")).scalar_one()
            moves = conn.execute(text("SELECT count(*) FROM game_moves")).scalar_one()
            evaluated = conn.execute(
                text("SELECT count(*) FROM game_moves WHERE eval_cp_before IS NOT NULL")
            ).scalar_one()
    finally:
        engine.dispose()
    return ServiceStatus(
        "postgres", True, f"{games} games, {moves} moves ({evaluated} evaluated)"
    )


def check_neo4j() -> ServiceStatus:
    from neo4j import READ_ACCESS, GraphDatabase

    from chess_mcp.config import get_neo4j_settings

    settings = get_neo4j_settings()
    driver = GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password))
    try:
        counts = {}
        with driver.session(database=settings.database, default_access_mode=READ_ACCESS) as session:
            for label in CHESS_LABELS:
                # Labels come from the constant above, never from input.
                record = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS c").single()
                counts[label] = record["c"] if record else 0
    finally:
        driver.close()
    detail = ", ".join(f"{label} {count}" for label, count in counts.items())
    return ServiceStatus("neo4j", counts["Position"] > 0, detail)


def check_stockfish() -> ServiceStatus:
    import chess.engine

    from chess_mcp.config import get_stockfish_settings

    path = get_stockfish_settings().path
    if not path.exists():
        return ServiceStatus("stockfish", False, f"binary not found at {path}")
    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    try:
        name = engine.id.get("name", "unknown engine")
    finally:
        engine.quit()
    return ServiceStatus("stockfish", True, name)


CHECKS: dict[str, Callable[[], ServiceStatus]] = {
    "postgres": check_postgres,
    "neo4j": check_neo4j,
    "stockfish": check_stockfish,
}


def collect(checks: dict[str, Callable[[], ServiceStatus]] = CHECKS) -> list[ServiceStatus]:
    results = []
    for name, check in checks.items():
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - a down service is a status, not a crash
            results.append(ServiceStatus(name, False, f"unreachable ({type(exc).__name__})"))
    return results


def render(results: list[ServiceStatus]) -> str:
    return "\n".join(
        f"[{'OK' if result.ok else 'DOWN'}] {result.service}: {result.detail}"
        for result in results
    )


def main() -> int:
    results = collect()
    print(render(results))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
