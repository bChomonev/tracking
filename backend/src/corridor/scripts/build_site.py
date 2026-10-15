"""Render the static site: the Premier League overview plus every team's breakdown, with
the analyst's read for the focus team.

    uv run python -m corridor.scripts.build_site [--season 2026]

Reads data/site/{season}/league.json (+ analysis.json if present) and writes
data/site/{season}/index.html (gitignored).
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from corridor.ingest.http import DATA_DIR

TEMPLATE = Path(__file__).resolve().parents[4] / "web" / "united.html"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()
    out = DATA_DIR / "site" / str(args.season)
    league = json.loads((out / "league.json").read_text())
    league["generated_at"] = datetime.now(UTC).isoformat()
    analysis_path = out / "analysis.json"
    analysis = json.loads(analysis_path.read_text()) if analysis_path.exists() else None

    def embed(obj: object) -> str:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")

    html = (
        TEMPLATE.read_text()
        .replace("/*__PROFILE__*/null", embed(league))
        .replace("/*__ANALYSIS__*/null", embed(analysis))
    )
    (out / "index.html").write_text(html)
    print(f"wrote {out / 'index.html'} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
