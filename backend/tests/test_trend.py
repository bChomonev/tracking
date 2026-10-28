"""Recent form (corridor.trend): the last matches against the earlier ones."""

from corridor import trend


def test_too_few_matches_gives_no_call():
    t = trend.recent([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])  # 7 < WINDOW + MIN_BEFORE
    assert t["n"] == 7 and t["call"] is None and t["delta"] is None
    assert t["recent"] == sum([0.3, 0.4, 0.5, 0.6, 0.7]) / 5
    assert t["before"] == (0.1 + 0.2) / 2  # shown, but not called
    assert trend.recent([]) is None
    assert trend.recent([None, None]) is None


def test_none_values_are_skipped_not_counted():
    t = trend.recent([None, 1.0, 1.0, 1.0, None, 1.0, 1.0, 1.0, 1.0, 1.0])
    assert t["n"] == 8 and t["series"] == [1.0] * 8


def test_a_clear_rise_is_called_up_and_a_wobble_is_steady():
    up = trend.recent([-1.0, -0.8, -1.2, -1.0, 0.8, 1.0, 1.2, 0.9, 1.1])
    assert up["call"] == "up" and up["delta"] > up["noise"] > 0
    down = trend.recent([v * -1 for v in up["series"]])
    assert down["call"] == "down"
    # Noisy series with no shift: the gap is inside one standard error.
    flat = trend.recent([1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
    assert flat["call"] == "steady"
    # No variation at all → steady, never a division by zero.
    assert trend.recent([0.5] * 9)["call"] == "steady"


def test_words_say_both_numbers_and_the_window():
    t = trend.recent([0.1, 0.1, 0.1, 0.2, 0.9, 0.9, 0.9, 0.9, 0.9])
    s = trend.words(t, "Elite score", decimals=2)
    assert s.startswith(
        "Elite score: better over the last 5 matches, 0.90 against 0.12 in the 4 before"
    )
    # Lower is better flips the wording, not the numbers.
    s2 = trend.words(t, "Danger score", decimals=2, lower_is_better=True)
    assert s2.startswith("Danger score: worse over the last 5 matches, 0.90 against 0.12")
    assert trend.words(trend.recent([0.1, 0.2]), "x") is None
