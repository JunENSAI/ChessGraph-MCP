"""Graph writer and loader guards with a fake Neo4j driver (no database)."""

from __future__ import annotations

import re
from dataclasses import fields
from types import SimpleNamespace
from typing import Any

from etl.neo4j_db.neo4j_load import other_label_changes
from etl.neo4j_db.transform import GraphPayload
from etl.neo4j_db.write import (
    CHESS_LABELS,
    SCHEMA,
    STEPS,
    batches,
    meta_properties,
    reset_chess_graph,
    write_graph,
)


class FakeResult:
    def __init__(self, deleted: int = 0) -> None:
        self._deleted = deleted

    def consume(self) -> Any:
        return SimpleNamespace(counters=SimpleNamespace(nodes_deleted=self._deleted))


class FakeTx:
    def __init__(self, log: list[tuple[str, dict[str, Any]]]) -> None:
        self.log = log

    def run(self, query: str, **params: Any) -> FakeResult:
        self.log.append((query, params))
        return FakeResult()


class FakeSession:
    def __init__(self, log: list[tuple[str, dict[str, Any]]]) -> None:
        self.log = log

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def run(self, query: str, **params: Any) -> FakeResult:
        self.log.append((query, params))
        return FakeResult(deleted=3)

    def execute_write(self, work: Any, *args: Any) -> Any:
        return work(FakeTx(self.log), *args)


class FakeDriver:
    def __init__(self) -> None:
        self.log: list[tuple[str, dict[str, Any]]] = []

    def session(self, **_: Any) -> FakeSession:
        return FakeSession(self.log)


def empty_payload(**rows: list[dict[str, Any]]) -> GraphPayload:
    values: dict[str, Any] = {f.name: [] for f in fields(GraphPayload)}
    values.update(rows)
    values["meta"] = {"schema_version": 2, "loaded_at": "2026-11-22T00:00:00+00:00", "counts": {}}
    payload = GraphPayload(**values)
    payload.meta["counts"] = payload.counts()
    return payload


def test_every_payload_list_has_a_write_step_and_nodes_come_first() -> None:
    lists = {f.name for f in fields(GraphPayload) if f.name != "meta"}
    names = [name for name, _ in STEPS]
    assert set(names) == lists
    assert names.index("positions") < names.index("played_moves")
    assert names.index("games") < names.index("reached")
    assert names.index("players") < names.index("played_as")


def test_every_statement_touches_only_chess_labels() -> None:
    labels = set()
    for _, query in STEPS:
        labels.update(re.findall(r"\(\w*:(\w+)", query))
    for statement in SCHEMA:
        labels.update(re.findall(r"\(\w*:(\w+)\)", statement))
    assert labels <= set(CHESS_LABELS)
    assert "DELETE" not in " ".join(query for _, query in STEPS)


def test_reset_deletes_only_the_chess_labels_in_batched_transactions() -> None:
    driver = FakeDriver()
    deleted = reset_chess_graph(driver)  # type: ignore[arg-type]
    assert list(deleted) == list(CHESS_LABELS)
    assert len(driver.log) == len(CHESS_LABELS)
    for (query, _), label in zip(driver.log, CHESS_LABELS, strict=True):
        assert query.startswith(f"MATCH (n:`{label}`) CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS")


def test_write_graph_batches_rows_and_writes_meta() -> None:
    driver = FakeDriver()
    positions = [{"fen_norm": f"p{i}"} for i in range(5)]
    payload = empty_payload(positions=positions)
    sent = write_graph(driver, payload, batch_size=2)  # type: ignore[arg-type]

    assert sent["positions"] == 5
    position_calls = [params["rows"] for query, params in driver.log if "MERGE (p:Position" in query]
    assert [len(rows) for rows in position_calls] == [2, 2, 1]
    meta_query, meta_params = driver.log[-1]
    assert "ChessGraphMeta" in meta_query
    assert meta_params["props"]["schema_version"] == 2
    assert meta_params["props"]["count_positions"] == 5
    # Empty steps send nothing.
    assert not any("PLAYED_MOVE" in query for query, _ in driver.log)


def test_meta_properties_are_flat() -> None:
    props = meta_properties(empty_payload(games=[{"game_id": 1}]))
    assert props["count_games"] == 1
    assert all(not isinstance(value, dict) for value in props.values())


def test_batches_split_evenly() -> None:
    assert [list(b) for b in batches([1, 2, 3], 2)] == [[1, 2], [3]]
    assert batches([], 2) == []


def test_other_label_changes_ignores_chess_labels() -> None:
    before = {"Position": 10, "Paper": 5, "Author": 2}
    after = {"Position": 99, "Paper": 5, "Author": 2, "Player": 4}
    assert other_label_changes(before, after) == {}
    assert other_label_changes(before, {**after, "Paper": 4}) == {"Paper": (5, 4)}
    assert other_label_changes(before, {"Position": 1}) == {"Author": (2, 0), "Paper": (5, 0)}
