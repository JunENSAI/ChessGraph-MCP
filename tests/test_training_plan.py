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


# --- build_program -------------------------------------------------------

from chess_mcp.postgres.training_plan import PROGRAM_DAYS, build_program  # noqa: E402

CARO_LINE = "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4"
BLACK_FEN = "rn1qkbnr/pp2pppp/2p5/5b2/3PN3/8/PPP2PPP/R1BQKBNR b KQkq -"
WHITE_FEN = "rnbqkbnr/pp1ppppp/2p5/8/3PP3/8/PPP2PPP/RNBQKBNR w KQkq -"


def _caro_plan():
    rows = [row for row in _family("Caro-Kann Defense", "black", 4, 0, 9)]
    rows += [row for row in _family("London System", "white", 14, 3, 6)]
    # The family's first stored line is too short, as in the real catalog.
    return rank_plan(family_rows=rows, theory_rows=[("Caro-Kann Defense", "e2e4 c7c6", ""), ("London System", "d2d4 d7d5 c1f4 g8f6 e2e3 e7e6", "")])


def _split(fen: str, san: str, best: str, times: int, cp: int, name: str = "Caro-Kann Defense: Main Line") -> tuple:
    return (name, fen, 9, san, "a1a1", best, times, cp)


def test_program_has_seven_days_on_the_top_family_with_its_most_played_long_line() -> None:
    lines = [
        ("Caro-Kann Defense", "black", 141, "e2e4 c7c6"),
        ("Caro-Kann Defense: Main Line", "black", 60, CARO_LINE),
        ("Caro-Kann Defense: Advance Variation", "black", 20, "e2e4 c7c6 d2d4 d7d5 e4e5 c8f5"),
    ]
    program = build_program(_caro_plan(), lines=lines, average_rating=1835.6)
    assert program.focus == "Caro-Kann Defense"
    # The short base line is skipped for the most played variant that can be drilled.
    assert program.title == "Caro-Kann Defense: Main Line"
    assert program.user_color == "black"
    assert [day.day for day in program.days] == list(range(1, PROGRAM_DAYS + 1))
    assert [day.kind for day in program.days][:2] == ["learn", "drill"]
    assert program.days[-1].kind == "review"
    assert all(day.uci_line == CARO_LINE and day.user_color == "black" for day in program.days)
    plays = [day for day in program.days if day.kind == "play"]
    assert len(plays) == 2 and {day.opponent_elo for day in plays} == {1836}
    assert "4 wins, 0 draws, 9 losses" in program.days[-1].goal


def test_program_mistakes_are_the_costly_repeats_with_you_to_move() -> None:
    lines = [("Caro-Kann Defense: Main Line", "black", 60, CARO_LINE)]
    splits = [
        _split(BLACK_FEN, "Bg6", "h7h6", 6, 121),
        _split(BLACK_FEN, "Bg6", "h7h6", 2, 90),  # same position, lower total cost: dropped
        _split(BLACK_FEN.replace("5b2", "8"), "Nf6", "e7e5", 4, 97),
        _split(BLACK_FEN.replace("pp2", "p3"), "c6", "c7c5", 106, 10),  # under an inaccuracy
        _split(WHITE_FEN, "e5", "g1f3", 9, 200),  # the opponent to move
        _split(BLACK_FEN, "Bg4", "h7h6", 9, 300, name="Scandinavian Defense"),  # another family
    ]
    program = build_program(_caro_plan(), lines=lines, split_rows=splits)
    mistakes = [day for day in program.days if day.kind == "mistakes"]
    assert [day.day for day in mistakes] == [3, 5]
    assert [(item.played_san, item.times, item.average_cp_loss) for item in mistakes[0].positions] == [
        ("Bg6", 6, 121),
        ("Nf6", 4, 97),
    ]


def test_program_drills_again_when_no_mistake_is_stored() -> None:
    lines = [("Caro-Kann Defense: Main Line", "black", 60, CARO_LINE)]
    program = build_program(_caro_plan(), lines=lines, split_rows=[], average_rating=None)
    assert [day.kind for day in program.days] == ["learn", "drill", "drill", "play", "drill", "play", "review"]
    assert all(day.opponent_elo is None for day in program.days)
    assert any("No repeated move" in note for note in program.notes)


def test_program_falls_back_to_the_next_family_with_a_line() -> None:
    # No Caro-Kann line long enough: the London item, ready on its own line, becomes the focus.
    program = build_program(_caro_plan(), lines=[("Caro-Kann Defense", "black", 141, "e2e4 c7c6")])
    assert program.focus == "London System"
    assert program.user_color == "white"


def test_program_is_empty_without_a_drillable_line() -> None:
    rows = [row for row in _family("Caro-Kann Defense", "black", 4, 0, 9)]
    program = build_program(rank_plan(family_rows=rows), lines=[])
    assert program.focus is None and program.days == []
    assert program.notes
