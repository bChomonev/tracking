import numpy as np

from corridor import mistakes as M


def test_miss_kind_reads_the_xg_from_the_favourites_side():
    # Home favourite lost: away won xG by 1.0 → deserved; home won it by 1.0 → luck.
    assert M.miss_kind(0, 0.8, 1.8) == "deserved"
    assert M.miss_kind(0, 1.8, 0.8) == "luck"
    assert M.miss_kind(0, 1.2, 1.4) == "close"
    # Away favourite: the underdog is the home side.
    assert M.miss_kind(2, 1.8, 0.8) == "deserved"
    assert M.miss_kind(2, 1.0, None) is None


def _cal(rng, n, home_bias):
    """One season of matches where home favourites lose more often than we say."""
    test, probs = [], []
    for i in range(n):
        p = np.array([0.65, 0.2, 0.15])
        r = rng.random()
        res = "A" if r < 0.15 + home_bias else "D" if r < 0.35 + home_bias else "H"
        test.append(
            {
                "id": str(i),
                "kickoff": f"2020-01-{i % 28 + 1:02d}",
                "home": f"T{i % 10}",
                "away": f"T{(i + 1) % 10}",
                "result": res,
                "rows": {},
            }
        )
        probs.append(p)
    pm = np.array(probs)
    return test, pm, pm, 1.0


def test_slices_flag_a_real_bias_and_not_a_fair_one():
    rng = np.random.default_rng(42)
    biased = {s: _cal(rng, 400, 0.08) for s in (2020, 2021, 2022)}
    scored = [m for t, *_ in biased.values() for m in t]
    for m, s in zip(scored, [s for s in biased for _ in range(400)], strict=True):
        m["season"] = s
    sl = {s["slice"]: s for s in M.slices(M.rows(biased, [2020, 2021, 2022], scored))}
    assert sl["Home favourite"]["flag"] and sl["Home favourite"]["z"] > 0

    fair = {s: _cal(rng, 400, 0.0) for s in (2020, 2021, 2022)}
    scored = [m for t, *_ in fair.values() for m in t]
    for m, s in zip(scored, [s for s in fair for _ in range(400)], strict=True):
        m["season"] = s
    sl = {s["slice"]: s for s in M.slices(M.rows(fair, [2020, 2021, 2022], scored))}
    assert not sl["Home favourite"]["flag"]


def test_home_edge_test_learns_only_from_earlier_seasons():
    rng = np.random.default_rng(42)
    cal = {s: _cal(rng, 400, 0.08) for s in (2019, 2020, 2021)}
    t = M.home_edge_test(cal, [2020, 2021], 2019)
    assert set(t["k"]) == {2020, 2021}  # 2019 has nothing before it to learn from
    assert t["k"][2020] > 1 and t["helps"]


def test_bands_compare_what_we_said_with_what_happened():
    rs = [
        {"p_fav": 0.75, "p_dog": 0.1, "won": True, "lost": False},
        {"p_fav": 0.72, "p_dog": 0.12, "won": False, "lost": False},  # a draw
        {"p_fav": 0.45, "p_dog": 0.3, "won": False, "lost": True},
    ]
    b = M.bands(rs)
    top = b["win"][0]
    assert (top["from"], top["n"], top["happened"]) == (0.7, 2, 0.5)
    dc = {(x["from"], x["to"]): x for x in b["win_or_draw"]}
    assert dc[(0.85, 0.9)]["happened"] == 1.0 and dc[(0.85, 0.9)]["n"] == 1
    assert dc[(0.7, 0.75)]["happened"] == 0.0  # 1 - 0.3 = 0.7: the favourite lost
