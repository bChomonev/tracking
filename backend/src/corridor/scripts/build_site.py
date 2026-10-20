"""Render the static site: the Premier League overview plus every team's breakdown, with
the analyst's read for the focus team.

    uv run python -m corridor.scripts.build_site [--season 2026]

Reads data/site/{season}/league.json (+ predictions.json, previews.json and analysis.json
if present) and writes data/site/{season}/index.html (gitignored).
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from corridor import cup
from corridor.ingest import fotmob
from corridor.ingest.http import DATA_DIR
from corridor.leagues import LEAGUES, site_dir

TEMPLATE = Path(__file__).resolve().parents[4] / "web" / "united.html"


def add_next_cup(leagues: dict, season: int, now: str) -> None:
    """Each focus team's next Champions League game, fixture and numbers only (D-049)."""
    rows_path = DATA_DIR / "processed" / str(season) / "ucl" / "team_matches.json"
    if not rows_path.exists():
        return
    rows = json.loads(rows_path.read_text())
    teams = {r["team"] for r in rows}
    if not any(lg.get("focus_team") in teams for lg in leagues.values()):
        return
    try:
        fixtures = fotmob.league_matches(f"{season}/{season + 1}", fotmob.CHAMPIONS_LEAGUE)
    except Exception as e:  # noqa: BLE001 — no fixture list → no card, the site still builds
        print(f"next Champions League game skipped: {e}")
        return
    for lg in leagues.values():
        if lg.get("focus_team") in teams:
            lg["next_cup"] = cup.next_cup_match(lg["focus_team"], fixtures, leagues, rows, now)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()
    out = DATA_DIR / "site" / str(args.season)
    leagues = {}
    for key, lg in LEAGUES.items():
        d = site_dir(args.season, lg)
        if not (d / "league.json").exists():
            continue  # league not built yet
        league = json.loads((d / "league.json").read_text())
        for name in ("predictions", "previews"):
            if (d / f"{name}.json").exists():
                league[name] = json.loads((d / f"{name}.json").read_text())
        leagues[key] = league
    now = datetime.now(UTC)
    add_next_cup(leagues, args.season, now.isoformat())
    site = {"generated_at": now.isoformat(), "leagues": leagues}
    analysis_path = out / "analysis.json"
    analysis = json.loads(analysis_path.read_text()) if analysis_path.exists() else None

    def embed(obj: object) -> str:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")

    html = (
        TEMPLATE.read_text()
        .replace("/*__PROFILE__*/null", embed(site))
        .replace("/*__ANALYSIS__*/null", embed(analysis))
    )
    (out / "index.html").write_text(html)
    print(f"wrote {out / 'index.html'} ({len(html) // 1024} KB; leagues: {', '.join(leagues)})")


if __name__ == "__main__":
    main()
