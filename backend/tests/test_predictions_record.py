from corridor.scripts.predictions import fotmob_result, score_from_fotmob


def _fm(home, away, score, finished=True):
    return {
        "home": {"name": home},
        "away": {"name": away},
        "status": {"finished": finished, "cancelled": False, "scoreStr": score},
    }


def test_fotmob_result_reads_the_final_score_only():
    assert fotmob_result(_fm("A", "B", "4 - 4")) == ("D", "4-4")
    assert fotmob_result(_fm("A", "B", "0 - 2")) == ("A", "0-2")
    assert fotmob_result(_fm("A", "B", "1 - 0", finished=False)) is None
    assert fotmob_result({"home": {}, "away": {}, "status": {"finished": True}}) is None


def test_score_from_fotmob_fills_only_unscored_entries_and_tags_them():
    log = {
        "1": {"home": "A", "away": "B", "p": [0.6, 0.2, 0.2], "p_noform": [0.5, 0.3, 0.2]},
        "2": {"home": "C", "away": "D", "p": [0.3, 0.3, 0.4], "result": "H", "rps": 0.1},
        "3": {"home": "E", "away": "F", "p": [0.3, 0.3, 0.4]},
    }
    fm = [_fm("A", "B", "2 - 0"), _fm("C", "D", "0 - 1"), _fm("E", "F", "0 - 0", finished=False)]
    assert score_from_fotmob(log, fm) == 1
    assert log["1"]["result"] == "H" and log["1"]["score"] == "2-0"
    assert log["1"]["scored_from"] == "fotmob"
    assert log["1"]["rps"] < log["1"]["rps_noform"]  # the sharper pick scores better
    assert log["2"] == {"home": "C", "away": "D", "p": [0.3, 0.3, 0.4], "result": "H", "rps": 0.1}
    assert "result" not in log["3"]
