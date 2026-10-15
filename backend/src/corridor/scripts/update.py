"""Rebuild (and optionally republish) the United page after each new United match.

    uv run python -m corridor.scripts.update [--publish] [--force] [--check]

Meant to run on a schedule (see ops/launchd). Each run:
1. Refreshes the PL and UCL fixture lists (2 requests) and finds United's finished matches.
2. Decides whether a new match is *ready*: FotMob stats ~3 h after kickoff for the PL; UEFA
   tracking ~17 h after kickoff for the UCL. Not ready → exit quietly.
3. Runs build_season (pl, ucl) → united_profile → analyse → build_site.
   If Understat hasn't published the new PL match yet (no PPDA), waits for a later run,
   up to UNDERSTAT_MAX_WAIT.
4. With --publish, starts a background Claude Code session that republishes the page to the
   artifact (only Claude can publish artifacts), and shows a macOS notification.
State lives in data/site/{season}/update_state.json; logs in data/logs/update.log.
"""

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from corridor.ingest import fotmob
from corridor.ingest.http import DATA_DIR

TEAM = "Manchester United"
ARTIFACT_URL = "https://claude.ai/artifact/U17iYtvFhdCsqucR2iY4fT"
REPO = Path(__file__).resolve().parents[4]
READY_AFTER = {"pl": timedelta(hours=3), "ucl": timedelta(hours=18)}
UNDERSTAT_MAX_WAIT = timedelta(hours=48)
LEAGUES = {"pl": fotmob.PREMIER_LEAGUE, "ucl": fotmob.CHAMPIONS_LEAGUE}

log = logging.getLogger("update")


def united_finished(season: int) -> dict[str, list[dict]]:
    """{'pl': [{id, kickoff, opponent}], 'ucl': [...]} for United's finished matches."""
    out: dict[str, list[dict]] = {}
    for comp, league in LEAGUES.items():
        out[comp] = [
            {
                "id": int(m["id"]),
                "kickoff": m["status"]["utcTime"],
                "label": f"{m['home']['name']} {m['status'].get('scoreStr', '')} "
                f"{m['away']['name']}",
            }
            for m in fotmob.league_matches(f"{season}/{season + 1}", league)
            if TEAM in (m["home"]["name"], m["away"]["name"])
            and m["status"].get("finished")
            and not m["status"].get("cancelled")
        ]
    return out


def _kickoff(m: dict) -> datetime:
    return datetime.fromisoformat(m["kickoff"].replace("Z", "+00:00"))


def pending(finished: dict[str, list[dict]], state: dict, now: datetime) -> list[tuple]:
    """New United matches that are ready to build: [(comp, match)]."""
    return [
        (comp, m)
        for comp, ms in finished.items()
        for m in ms
        if m["id"] not in state.get(comp, []) and now - _kickoff(m) >= READY_AFTER[comp]
    ]


def understat_missing(season: int, match_ids: set[int]) -> list[int]:
    rows = json.loads((DATA_DIR / "processed" / str(season) / "team_matches.json").read_text())
    return [
        r["match_id"]
        for r in rows
        if r["team"] == TEAM and r["match_id"] in match_ids and r.get("ppda") is None
    ]


def run_step(module: str, *args: str) -> None:
    cmd = [sys.executable, "-m", f"corridor.scripts.{module}", *args]
    log.info("run %s", " ".join(cmd[2:]))
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO / "backend")
    for line in (res.stdout + res.stderr).strip().splitlines()[-6:]:
        log.info("  %s", line)
    if res.returncode:
        raise RuntimeError(f"{module} failed (exit {res.returncode})")


def notify(title: str, text: str) -> None:
    script = f"display notification {json.dumps(text)} with title {json.dumps(title)}"
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


PUBLISH_PROMPT = """\
Scheduled United page update. Republish the already-built page and do nothing else:
call the Artifact tool (action publish) with file_path {page} and url {url}, \
label "{label}". Do not edit any file, do not run the pipeline, do not commit. \
If publishing fails, say why in one line."""


CLAUDE = Path.home() / ".local" / "bin" / "claude"


def publish(page: Path, label: str, previous_session: str | None) -> str | None:
    """Hand the publish to a background Claude Code session (artifacts can only be published
    by Claude) and return its id. The previous run's session is removed first so they don't
    pile up in `claude agents`; sessions we didn't start are never touched."""
    if previous_session:
        subprocess.run([str(CLAUDE), "rm", previous_session], capture_output=True, check=False)
    prompt = PUBLISH_PROMPT.format(page=page, url=ARTIFACT_URL, label=label[:60])
    res = subprocess.run(
        [str(CLAUDE), "--bg", prompt], cwd=REPO, capture_output=True, text=True, timeout=120
    )
    if res.returncode:
        raise RuntimeError("could not start the publishing Claude session")
    m = re.search(r"backgrounded\W+([0-9a-f]{6,})", res.stdout)
    log.info("publish session: %s (claude logs %s)", m and m.group(1), m and m.group(1))
    return m.group(1) if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--publish", action="store_true", help="republish the artifact via Claude")
    ap.add_argument("--force", action="store_true", help="rebuild even without a new match")
    ap.add_argument("--check", action="store_true", help="only report what would happen")
    args = ap.parse_args()

    (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[
            logging.FileHandler(DATA_DIR / "logs" / "update.log"),
            logging.StreamHandler(),
        ],
    )
    site = DATA_DIR / "site" / str(args.season)
    state_path = site / "update_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    now = datetime.now(UTC)

    finished = united_finished(args.season)
    if not state:  # first run: everything already on the page counts as done
        state = {comp: [m["id"] for m in ms] for comp, ms in finished.items()}
        state_path.write_text(json.dumps(state, indent=1))
        log.info("initialised state with %s", {k: len(v) for k, v in state.items()})
    new = pending(finished, state, now)
    waiting = [
        m["label"]
        for comp, ms in finished.items()
        for m in ms
        if m["id"] not in state.get(comp, []) and (comp, m) not in new
    ]
    if waiting:
        log.info("finished but not ready yet: %s", "; ".join(waiting))
    if not new and not args.force:
        log.info("nothing new")
        return
    labels = [m["label"] for _, m in new] or ["manual rebuild"]
    log.info("updating for: %s", "; ".join(labels))
    if args.check:
        return

    try:
        run_step("build_season", "--season", str(args.season))
        new_pl = {m["id"] for comp, m in new if comp == "pl"}
        missing = understat_missing(args.season, new_pl)
        recent = [
            m for comp, m in new if m["id"] in missing and now - _kickoff(m) < UNDERSTAT_MAX_WAIT
        ]
        if recent and not args.force:
            log.info("Understat has no PPDA yet for %s; trying again next run", recent[0]["label"])
            return
        run_step("build_season", "--season", str(args.season), "--competition", "ucl")
        run_step("united_profile", "--season", str(args.season))
        try:
            run_step("analyse", "--season", str(args.season))
        except RuntimeError:
            log.info("analyst failed once; retrying")
            try:
                run_step("analyse", "--season", str(args.season))
            except RuntimeError:
                # Never ship a read written about older numbers: fall back to the rule-based
                # verdict on the page until the next successful run.
                stale = site / "analysis.json"
                if stale.exists():
                    stale.rename(site / "analysis.stale.json")
                log.info("analyst failed twice; publishing without the written read")
        run_step("build_site", "--season", str(args.season))
    except Exception as e:
        log.exception("update failed")
        notify("United page update failed", str(e)[:120])
        raise SystemExit(1) from e

    page = site / "index.html"
    digest = hashlib.sha256(page.read_bytes()).hexdigest()
    for comp, m in new:
        state.setdefault(comp, []).append(m["id"])
    state["last_build"] = {"at": now.isoformat(), "for": labels, "sha256": digest}
    state_path.write_text(json.dumps(state, indent=1))

    if args.publish:
        state["publish_session"] = publish(
            page, f"After {labels[-1]}", state.get("publish_session")
        )
        state_path.write_text(json.dumps(state, indent=1))
        notify("United page updated", f"After {labels[-1]} — publishing to claude.ai")
    else:
        notify("United page rebuilt", f"After {labels[-1]} (not published)")
    log.info("done")


if __name__ == "__main__":
    main()
