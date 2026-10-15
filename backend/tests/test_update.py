from datetime import UTC, datetime

from corridor.scripts.update import pending

NOW = datetime(2026, 10, 18, 20, 0, tzinfo=UTC)


def _m(i, kickoff):
    return {"id": i, "kickoff": kickoff, "label": str(i)}


def test_pl_ready_three_hours_after_kickoff_ucl_after_twelve():
    finished = {
        "pl": [
            _m(1, "2026-10-10T16:30:00Z"),
            _m(2, "2026-10-18T16:30:00Z"),
            _m(3, "2026-10-18T17:30:00Z"),
        ],
        "ucl": [_m(10, "2026-10-18T07:00:00Z"), _m(11, "2026-10-18T09:00:00Z")],
    }
    state = {"pl": [1], "ucl": []}
    got = [(c, m["id"]) for c, m in pending(finished, state, NOW)]
    assert got == [("pl", 2), ("ucl", 10)]  # 3 is 2.5 h old, 11 is 11 h old


def test_already_built_matches_are_skipped():
    finished = {"pl": [_m(1, "2026-10-10T16:30:00Z")], "ucl": []}
    assert pending(finished, {"pl": [1], "ucl": []}, NOW) == []
