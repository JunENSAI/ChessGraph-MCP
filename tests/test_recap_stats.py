from chess_mcp.postgres.recap import build_recap


def test_favorite_line_is_the_most_played_stored_name() -> None:
    rows = [
        ("1900-1999", "white", "Italian Game", "C50", "win", 2),
        ("1900-1999", "white", "Italian Game", "C50", "loss", 1),
        ("1900-1999", "white", "Queen's Pawn Game: London System", "D02", "win", 40),
        ("1900-1999", "white", "Queen's Pawn Game: London System", "D02", "loss", 10),
        ("1900-1999", "black", "Scandinavian Defense: Main Line", "B01", "win", 12),
        ("1900-1999", "black", "Caro-Kann Defense", "B10", "win", 5),
    ]
    payload = build_recap(rows, [("1900-1999", "rapid", "win", 70)]).model_dump(by_alias=True)
    band = next(item for item in payload["bands"] if item["id"] == "1900-1999")

    assert band["openingsWhite"][0]["name"] == "Queen's Pawn Game: London System"
    assert band["openingsWhite"][0]["results"] == {"wins": 40, "draws": 0, "losses": 10}
    assert band["white"] == {"wins": 42, "draws": 0, "losses": 11}
    assert band["defensesBlack"][0]["name"] == "Scandinavian Defense: Main Line"
    assert band["timeControls"][0]["label"] == "Rapid"
    assert band["timeControls"][0]["averageOpponentElo"] is None
    assert band["openingsWhite"][1]["name"] == "Italian Game"
    assert payload["gameCount"] == 70


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
