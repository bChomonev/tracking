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
