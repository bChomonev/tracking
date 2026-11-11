from corridor.scripts.united_profile import _expected_points


def test_expected_points_average_the_two_histories():
    x = {
        "best_weighted": {"history": {"n": 50, "W": 0.6, "D": 0.2}},
        "worst_weighted": {"history": {"n": 40, "W": 0.2, "D": 0.4}},
    }
    assert abs(_expected_points(x) - ((1.8 + 0.2) + (0.6 + 0.4)) / 2) < 1e-9
    empty = {"best_weighted": {"history": None}, "worst_weighted": {"history": {"n": 0}}}
    assert _expected_points(empty) is None


def test_odds_name_map_never_guesses_a_wrong_team():
    from corridor.ingest.odds import name_map

    ours = {
        "Wolverhampton Wanderers",
        "West Ham",
        "Leeds",
        "West Bromwich Albion",
        "Manchester United",
    }
    got = name_map({"Wolves", "West Ham", "Leeds", "West Brom", "Man United"}, ours)
    assert got["Wolves"] == "Wolverhampton Wanderers" and got["West Brom"] == "West Bromwich Albion"
    assert len(set(got.values())) == len(got)


def test_leagues_keep_their_data_apart():
    from corridor.leagues import LEAGUES, processed_dir, site_dir

    pl, es = LEAGUES["pl"], LEAGUES["laliga"]
    assert processed_dir(2026, pl) != processed_dir(2026, es)
    assert site_dir(2026, es).name == "laliga" and es.focus_team is None
    assert pl.focus_team == "Manchester United"


def test_spanish_odds_names_map_to_our_names():
    from corridor.ingest.odds import name_map

    ours = {
        "Atletico Madrid",
        "Athletic Club",
        "Real Madrid",
        "Real Betis",
        "Real Sociedad",
        "Racing Santander",
    }
    got = name_map(
        {"Ath Madrid", "Ath Bilbao", "Real Madrid", "Betis", "Sociedad", "Santander"}, ours
    )
    assert got == {
        "Ath Madrid": "Atletico Madrid",
        "Ath Bilbao": "Athletic Club",
        "Real Madrid": "Real Madrid",
        "Betis": "Real Betis",
        "Sociedad": "Real Sociedad",
        "Santander": "Racing Santander",
    }
