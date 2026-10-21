from chess_mcp.postgres.recap import ENDGAME_NOTE, build_coaching_brief, build_recap


def test_favorite_line_is_the_most_played_stored_name() -> None:
    rows = [
        ("1900-1999", "white", "Italian Game", "C50", "win", 2),
        ("1900-1999", "white", "Italian Game", "C50", "loss", 1),
        ("1900-1999", "white", "Queen's Pawn Game: London System", "D02", "win", 40),
        ("1900-1999", "white", "Queen's Pawn Game: London System", "D02", "loss", 10),
        ("1900-1999", "white", "London System", "A48", "win", 5),
        ("1900-1999", "black", "Scandinavian Defense: Main Line", "B01", "win", 12),
        ("1900-1999", "black", "Scandinavian Defense", "B01", "win", 4),
        ("1900-1999", "black", "Caro-Kann Defense", "B10", "win", 5),
    ]
    payload = build_recap(rows, [("1900-1999", "rapid", "win", 70)]).model_dump(by_alias=True)
    band = next(item for item in payload["bands"] if item["id"] == "1900-1999")

    assert band["openingsWhite"][0]["name"] == "London System"
    assert band["openingsWhite"][0]["eco"] == "D02"
    assert band["openingsWhite"][0]["results"] == {"wins": 45, "draws": 0, "losses": 10}
    assert band["white"] == {"wins": 47, "draws": 0, "losses": 11}
    assert band["defensesBlack"][0]["name"] == "Scandinavian Defense"
    assert band["defensesBlack"][0]["results"] == {"wins": 16, "draws": 0, "losses": 0}
    assert band["timeControls"][0]["label"] == "Rapid"
    assert band["timeControls"][0]["averageOpponentElo"] is None
    assert band["openingsWhite"][1]["name"] == "Italian Game"
    assert payload["gameCount"] == 79


def test_clock_profile_keeps_elo_averages_on_the_time_control() -> None:
    payload = build_recap(
        [],
        [
            ("1900-1999", "blitz", "win", 4),
            ("1900-1999", "blitz", "loss", 2),
        ],
        [("1900-1999", "blitz", 1710, 1820, 1650)],
    ).model_dump(by_alias=True)
    clock = next(item for item in payload["bands"] if item["id"] == "1900-1999")["timeControls"][0]

    assert clock["id"] == "blitz"
    assert clock["results"] == {"wins": 4, "draws": 0, "losses": 2}
    assert clock["averageOpponentElo"] == 1710
    assert clock["averageEloWhenWin"] == 1820
    assert clock["averageEloWhenLoss"] == 1650


START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


def test_coaching_brief_keeps_a_strength_and_the_london_split() -> None:
    brief = build_coaching_brief(
        [
            ("Italian Game", "white", "win", 10),
            ("Queen's Pawn Game: London System", "white", "win", 2),
            ("London System", "white", "loss", 6),
            ("Queen's Pawn Game: London System, with e6", "white", "loss", 2),
            ("Scotch Game", "white", "loss", 7),
            ("Caro-Kann Defense", "black", "win", 4),
            ("Caro-Kann Defense", "black", "draw", 4),
        ],
        [
            ("Queen's Pawn Game: London System", START, 5, "d4", "d2d4", "c2c4", 4, 40),
            ("London System", START, 7, "d4", "d2d4", "c2c4", 1, 80),
            ("London System", START, 3, "Nf3", "g1f3", "c2c4", 2, 20),
            ("Scotch Game", START, 4, "d4", "d2d4", "c2c4", 5, 30),
        ],
        [
            ("8/8/8/8/8/8/8/4K2k w - -", 24, "Ke2", "e1e2", "e1f1", 2, 150),
            (START, 30, "Qh5", "d1h5", "g1f3", 4, 9000),
        ],
    )

    assert brief.endgames == ENDGAME_NOTE
    assert [item.family for item in brief.strengths] == ["Italian Game", "Caro-Kann Defense"]
    assert brief.target is not None
    assert brief.target.family == "London System"
    assert brief.target.games == 10
    assert brief.target.wins == 2
    assert brief.target.losses == 8
    assert len(brief.target.splits) == 1
    split = brief.target.splits[0]
    assert split.played_uci == "d2d4"
    assert split.best_uci == "c2c4"
    assert split.best_san == "c4"
    assert split.times == 5
    assert split.average_cp_loss == 48
    assert split.mate is False
    assert brief.calculation[0].mate is True
    assert brief.calculation[0].played_san == "Qh5"
    assert brief.calculation[0].best_san == "Nf3"
    assert brief.calculation[1].times == 2
    assert brief.calculation[1].best_san == "Kf1"


def test_training_tasks_offer_a_new_opening_and_the_french() -> None:
    brief = build_coaching_brief(
        [
            ("Bird Opening", "white", "win", 7),
            ("Bird Opening", "white", "loss", 12),
            ("Italian Game", "white", "win", 2),
            ("Scandinavian Defense", "black", "win", 3),
            ("Scandinavian Defense", "black", "loss", 9),
            ("French Defense", "black", "win", 1),
            ("Caro-Kann Defense", "black", "win", 6),
        ],
        [],
        [],
        theory_rows=[
            ("French Defense: Winawer", "e2e4 e7e6", "1. e4 e6"),
            ("Sicilian Defense", "", ""),
            ("Italian Game", "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6", "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"),
            ("Bird Opening", "f2f4", "1. f4"),
        ],
        endgame_rows=[
            ("KQvK", "8/8/8/8/8/8/4K3/4k3 w - - 0 1", "e2d3", "1600-1800"),
            ("KQvKP", "8/8/8/8/8/5p2/4K3/4k3 w - - 0 1", "e2d2", "1600-1800"),
        ],
        puzzle_fens=["8/8/8/8/8/8/8/K6k w - -", START],
    )
    tasks = {task.kind: task for task in brief.tasks}

    assert tasks["opening"].title == "Italian Game"
    assert tasks["opening"].ready is True
    assert tasks["opening"].uci_line == "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6"
    assert "Bird Opening scores" in tasks["opening"].reason
    assert "7 wins" in tasks["opening"].reason
    assert tasks["defense"].title == "French Defense: Winawer"
    assert "Scandinavian Defense:" in tasks["defense"].reason
    assert "9 losses" in tasks["defense"].reason
    assert tasks["defense"].user_color == "black"
    assert tasks["endgame"].title == "KQvKP"
    assert tasks["endgame"].uci_line == "e2d2"
    assert "not stored on games" in tasks["endgame"].reason
    assert tasks["puzzle"].puzzle_fens == ["8/8/8/8/8/8/8/K6k w - -", START]
    assert tasks["puzzle"].uci_line == ""


def test_short_opening_line_is_not_ready() -> None:
    brief = build_coaching_brief(
        family_rows=[("Bird Opening", "white", "loss", 9), ("Bird Opening", "white", "win", 2)],
        split_rows=[],
        calculation_rows=[],
        theory_rows=[("King's Gambit", "e2e4 e7e5", "")],
    )
    opening = next(task for task in brief.tasks if task.kind == "opening")

    assert opening.title == "King's Gambit"
    assert opening.ready is False
    assert "2 plies" in opening.reason
