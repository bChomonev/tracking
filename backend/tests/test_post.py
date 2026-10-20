from corridor import post as POST
from corridor.scripts.post import check, to_markdown


def _post(text):
    return {
        "title": "T",
        "subtitle": "S",
        "sections": [{"heading": "H", "paragraphs": [text]}],
        "chart_captions": {},
    }


def test_numbers_must_come_from_the_fact_sheet():
    facts = {"match": {"xg_for": 0.8, "xg_against": 1.62}, "performance_score": {"elite_score": 16}}
    assert check(_post("United made 0.8 xG to Spurs' 1.62, an elite score of 16."), facts) == []
    problems = check(_post("United made 0.8 xG but 2.4 would have won it."), facts)
    assert problems and "2.4" in problems[0]
    assert check({"title": "no sections"}, facts)


def test_markdown_places_charts_and_the_ai_note():
    post = {
        "title": "T",
        "subtitle": "S",
        "sections": [{"heading": f"H{i}", "paragraphs": ["p"]} for i in range(4)],
        "chart_captions": {"lines": "L", "shots": "Sh", "xg": "X"},
    }
    md = to_markdown(post, {"lines": "lines.png", "shots": "shots.png", "xg": "xg.png"})
    assert md.index("## H0") < md.index("lines.png") < md.index("## H1") < md.index("shots.png")
    assert "AI assistant" in md


def test_standouts_count_ties_so_common_numbers_are_not_notable():
    from corridor.post import standouts

    # 30 full-backs' games: everyone dispossessed 0 times; duels won 1..30.
    pool = [
        {
            "match_id": i,
            "team": "X",
            "name": f"p{i}",
            "role": "FB",
            "minutes": 90,
            "duels_won": i,
            "dispossessed": 0,
        }
        for i in range(1, 31)
    ]
    me = {
        "match_id": 99,
        "team": "Us",
        "name": "Dalot",
        "role": "FB",
        "minutes": 90,
        "duels_won": 31,
        "dispossessed": 0,
    }
    (row,) = standouts(pool + [me], 99, "Us")
    assert [t["stat"] for t in row["best_of_the_season_for_his_role"]] == ["duels won"]
    best = row["best_of_the_season_for_his_role"][0]
    assert best["games_with_better"] == 0 and best["games_with_the_same"] == 0
    assert best["games_compared"] == 30


def test_ucl_view_keeps_league_lines_but_not_for_uefa_running():
    from corridor.post import ucl_view

    line = {"value": 1.0}
    prof = {
        "metrics": [
            {"key": "npxg", "best_line": line, "worst_line": line, "impact": {"tier": "decisive"}},
            {
                "key": "distance_gap_km",
                "best_line": line,
                "worst_line": line,
                "impact": {"tier": "decisive"},
            },
        ],
        "ucl": {"matches": [], "metrics": [{"key": "npxg"}, {"key": "distance_gap_km"}]},
    }
    by = {m["key"]: m for m in ucl_view(prof)["metrics"]}
    assert by["npxg"]["best_line"] == line and by["npxg"]["impact"]["tier"] == "decisive"
    assert by["distance_gap_km"]["best_line"] is None and by["distance_gap_km"]["impact"] is None


def test_note_numbers_and_chart_values_must_come_from_the_fact_sheet(tmp_path):
    from corridor.post import chart_note
    from corridor.scripts.post import check_notes

    facts = {"match": {"xg_for": 0.92, "xg_against": 1.41}, "set_pieces": 1.187}
    ok = {
        "notes": [
            {
                "text": "Leeds' chances were worth 1.41 goals; ours 0.92.",
                "chart": {
                    "bars": [{"label": "Leeds", "value": 1.41}, {"label": "Us", "value": 0.92}],
                    "reference": None,
                },
            }
        ]
    }
    assert check_notes(ok, facts) == []
    bad = {
        "notes": [
            {"text": "Ours were worth 0.92.", "chart": {"bars": [{"label": "x", "value": 2.7}]}}
        ]
    }
    assert "2.7" in check_notes(bad, facts)[0]
    assert check_notes({"notes": []}, facts)
    chart_note(ok["notes"][0]["chart"] | {"title": "T", "unit": "goals"}, tmp_path / "n.png")
    assert (tmp_path / "n.png").stat().st_size > 1000


def test_seo_puts_home_side_first_and_uses_search_names():
    facts = {
        "team": "Manchester United",
        "competition": "Premier League",
        "match": {
            "opponent": "Leeds United",
            "venue": "away",
            "date": "2026-10-18",
            "score": "2-1",
            "xg_for": 0.92,
            "xg_against": 1.41,
            "possession_pct": 39.0,
        },
        "running_vs_opponent": {"distance_more_than_opponent_km": -4.2},
    }
    s = POST.seo(facts)
    assert s["title"] == "Leeds United 1-2 Man Utd: xG, stats and who stood out"
    assert (
        "18 Oct 2026" in s["description"]
        and "out-run by Leeds United by 4.2 km" in s["description"]
    )
    assert len(s["description"]) <= 160
    assert s["slug"] == "leeds-united-1-2-man-utd-xg-stats"
