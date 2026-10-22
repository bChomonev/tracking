import pytest

from corridor.analyst.validate import check, is_supported, numbers_in

FACTS = {
    "metrics": [
        {"key": "npxg_per_shot", "typical_match": 0.074, "league_rank": 20},
        {"key": "distance_gap_km", "typical_match": -1.8},
    ],
    "players": [{"name": "Kobbie Mainoo", "per_90": {"Recoveries / 90": {"value": 10.1}}}],
    "record": {"played": 6, "goals_for": 9, "xg_for": 10.69},
}
ALLOWED = {0.074, 20.0, 1.8, 10.1, 6.0, 9.0, 10.69}


def good():
    return {
        "headline": "Worst shot quality in the league: 0.074 npxG per shot, 20th of 20.",
        "summary": "Out-run by 1.8 km per match.",
        "findings": [
            {
                "kind": "problem",
                "title": "Shots",
                "text": "0.07 per shot.",
                "interpretation": None,
                "evidence": ["npxg_per_shot"],
            }
        ],
        "players": [{"name": "Kobbie Mainoo", "kind": "positive", "text": "10.1 recoveries."}],
    }


@pytest.mark.parametrize(
    ("token", "ok"),
    [
        ("0.074", True),
        ("0.07", True),
        ("0.1", True),
        ("20", True),
        ("1.8", True),
        ("-1.8", True),
        ("10.69", True),
        ("10.7", True),
        ("11", True),
        ("4.7", False),
        ("0.08", False),
        ("7", False),
    ],
)
def test_is_supported_respects_quoted_precision(token, ok):
    assert is_supported(token, ALLOWED) is ok


def test_numbers_in_ignores_words_with_digits():
    assert numbers_in("ranked 20th, xG 1.65, U23 side, 5-2 win") == ["20", "1.65", "5", "2"]


def test_grounded_analysis_passes():
    assert check(good(), FACTS) == []


def test_invented_number_is_rejected():
    a = good()
    a["findings"][0]["text"] = "They ran 4.7 km less than Spurs."
    (problem,) = check(a, FACTS)
    assert "4.7" in problem


def test_bad_evidence_kind_and_player_are_rejected():
    a = good()
    a["findings"][0].update(kind="disaster", evidence=["made_up_metric"])
    a["players"][0]["name"] = "Some Player"
    problems = " | ".join(check(a, FACTS))
    assert "kind" in problems and "made_up_metric" in problems and "Some Player" in problems


def test_ellipsis_artifact_is_rejected():
    a = good()
    a["players"][0]["text"] = "His 10.1... his recoveries are strong."
    assert any("ellipsis" in p for p in check(a, FACTS))


def test_fact_rounding_matches_the_page():
    from corridor.analyst.facts import _r

    assert _r(98.5, 0) == 99 and _r(0.0745, 3) == 0.075 and _r(-2.25, 1) == -2.3
    assert _r(None, 1) is None


def test_slim_facts_drops_only_the_per_match_lists():
    from corridor.analyst.writer import slim_facts

    facts = {"metrics": [{"key": "a", "typical_match": 1, "per_match": [1, 2]}], "record": {"x": 1}}
    slim = slim_facts(facts)
    assert slim["metrics"] == [{"key": "a", "typical_match": 1}] and slim["record"] == {"x": 1}
    assert "per_match" in facts["metrics"][0]  # the original is untouched
