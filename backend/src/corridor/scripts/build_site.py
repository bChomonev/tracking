"""Render the static United page from the season profile.

    uv run python -m corridor.scripts.build_site [--season 2026]

Reads data/site/{season}/profile.json, writes data/site/{season}/index.html (gitignored).
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
    profile = json.loads((out / "profile.json").read_text())
    profile["generated_at"] = datetime.now(UTC).isoformat()
    payload = json.dumps(profile, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("/*__PROFILE__*/null", payload)
    (out / "index.html").write_text(html)
    print(f"wrote {out / 'index.html'} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
