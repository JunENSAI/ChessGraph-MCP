from chess_mcp.postgres.coaching_common import MIN_DRILL_PLIES, line_plies
from chess_mcp.postgres.training_plan import plan_weights, rank_plan


def _family(name: str, color: str, wins: int, draws: int, losses: int) -> tuple:
    return (name, color, "win", wins), (name, color, "draw", draws), (name, color, "loss", losses)


def test_line_plies_counts_tokens() -> None:
    assert line_plies("e2e4 e7e5 g1f3") == 3
    assert line_plies("") == 0
    assert line_plies("e2e4, e7e5;  g1f3") == 3


def test_short_line_is_not_drillable() -> None:
    rows = [row for row in _family("King's Gambit", "white", 2, 0, 9)]
    plan = rank_plan(family_rows=rows, theory_rows=[("King's Gambit", "e2e4 e7e5", "")])
    item = next(entry for entry in plan.items if entry.kind == "opening")
    assert item.ready is False
    assert str(MIN_DRILL_PLIES) in item.reason


def test_worst_scoring_family_ranks_first() -> None:
    rows = [row for row in _family("London System", "white", 14, 3, 6)]
    rows += [row for row in _family("King's Gambit", "white", 2, 0, 9)]
    rows += [row for row in _family("Caro-Kann Defense", "black", 11, 4, 9)]
    rows += [row for row in _family("Scandinavian Defense", "black", 12, 2, 10)]
    plan = rank_plan(family_rows=rows)
    assert plan.items[0].title == "King's Gambit"
    assert plan.items[0].weight > plan.items[1].weight


def test_weights_are_published_and_add_up() -> None:
    weights = plan_weights()
    # Tolerance, not equality: summing floats in a different order can differ in the last bit.
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert set(weights) == {"volume", "score", "cp_loss", "short_line"}
