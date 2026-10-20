"""Draft a post-match blog post (Substack) for the focus team (D-034).

    uv run python -m corridor.scripts.post [--league pl] [--team "Manchester United"]
        [--match <fotmob id> | latest]

Writes data/posts/{season}/{date}-{opponent}/: post.md, post.html (open it, copy, paste
into the Substack editor — images come along), post.json and the chart PNGs. A draft for
a human to edit, never published automatically. Numbers are checked against the fact
sheet and a critic pass flags claims the data doesn't support.
"""

import argparse
import html
import json
import re
import time
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from openai import APIConnectionError, APIStatusError, OpenAI

from corridor import post as POST
from corridor.analyst.validate import allowed_numbers, is_supported, numbers_in
from corridor.analyst.writer import TruncatedError, _complete, _parse_json
from corridor.config import settings
from corridor.ingest import fotmob
from corridor.ingest.http import DATA_DIR
from corridor.leagues import LEAGUES, processed_dir, site_dir

STYLE = (Path(__file__).resolve().parents[1] / "prompts" / "house_style.md").read_text()
TIMEOUT_S = 170  # the LLM gateway cuts requests at 180 s

PLAN = """\
You plan a post-match column. Read the HOUSE STYLE and the FACT SHEET (JSON, your only \
source) and return the plan, not the column.

Return ONLY JSON:
{"angle": "one sentence: the argument of the column",
 "title": "max 10 words", "subtitle": "one sentence",
 "opener": "the one-line friendly greeting (vary it)",
 "sections": [{"heading": "short", "bullets": ["point, with the exact number(s) it uses"]}],
 "numbers_used": ["every number the column will quote, exactly as in the fact sheet"]}
4-6 sections, 2-4 bullets each, at most about a dozen numbers in total, plus the player \
numbers in a "Who stood out" section built from "standouts" (each with its yardstick). \
Bullets state facts from the sheet or clearly-labelled opinion. Nothing from \
"not_measured" as fact."""

DRAFT = """\
You write the column from an approved PLAN, in the HOUSE STYLE. 600-900 words.
Every sentence must come from a plan bullet, or be clearly marked as my opinion ("I \
think", "to me", "I suspect"). Quote the plan's numbers exactly; add no new numbers and no \
new facts — in particular nothing about how the match flowed (stretches, momentum, who \
was on top when), goalkeepers, tactics or mood unless a plan bullet states it.

Return ONLY JSON:
{"title": "...", "subtitle": "...", "sections": [{"heading": "...", "paragraphs": ["..."]}]}
The first paragraph starts with the plan's opener. Don't add a data-source line; the \
pipeline adds it."""

REVISE = """\
An editor flagged sentences in this column as not supported by the data. Rewrite only \
those sentences: drop them, or turn them into clearly-marked opinion ("I think …"), or \
replace them with what the FACT SHEET actually says. Keep everything else word for word; \
add no new numbers. Return the whole column as the same JSON."""

CRITIC = """\
You check a football column against the FACT SHEET it was written from. List every \
statement presented as fact that the sheet does not support: it describes something the \
sheet has no data on (anything in "not_measured" counts), contradicts the sheet, or claims \
a cause the numbers don't show. Clearly-signalled opinion is fine. Ignore style and \
numbers (checked separately).
Return ONLY JSON: {"unsupported": [{"claim": "exact quote", "reason": "..."}]}"""


NOTES = """\
You write two short Substack Notes (social posts inside Substack) about this match, from \
the FACT SHEET only, in the HOUSE STYLE's voice and number rules. Notes are how new readers \
find the newsletter, so each must make sense to a United fan who has never heard of it. \
Two per match, never more: the column must not turn into spam.

Return ONLY JSON:
{"notes": [{"kind": "with the column" | "midway",
            "text": "the Note",
            "chart": null | {"title": "short", "unit": "goals" | "km" | "%" | "",
                             "bars": [{"label": "short", "value": number}],
                             "reference": null | {"label": "short", "value": number}}}]}

1. "with the column": posted with the column (Substack attaches the post's card, so no \
chart). The column's question and its short answer, plus the one number that makes the \
case, in 2-3 sentences.
2. "midway": posted halfway to the next match, standing on its own (no link). The single \
most striking number from the match that the column didn't lead with, with a chart of 2-4 \
bars (us vs them, or us vs the top four / bottom four). End with one sentence on why it \
matters for the next match, or a real question to fans.
Rules: at most about 280 characters of text each. Every number as in the fact sheet, \
rounded the way a fan says it (1.19 goals, not 1.187; 21 metres, not 21.31), and every \
comparison with both sides spelled out. Readers are strangers: never write "elite line" \
or "worst line" bare; say what it is ("what last season's top four managed in a typical \
win", "what the bottom four did in a typical defeat"), and label chart bars the same way \
("Top four, typical win"). Explain any other jargon in passing. Days of the week only from \
"weekday" fields. No hashtags, no emojis, no hype. Opinion is marked as opinion. \
Nothing from "not_measured" as fact. Chart values must be numbers from the fact sheet."""


REDDIT = """\
You write a Reddit post and a Reddit comment about this match for United fans (r/reddevils), \
from the FACT SHEET only, in the HOUSE STYLE's number rules but Reddit's tone: a fan who \
counts things, talking to other fans. Reddit removes or ignores link-dumps, so the post must \
be worth reading without clicking anything.

Return ONLY JSON:
{"title": "the post title", "body": "the post, Reddit markdown",
 "chart": "lines" | "shots" | "xg", "comment": "the comment"}

title: plain and specific, with the teams and the finding, e.g. "Leeds 1-1 United: we were \
out-run for the 6th time in 7 league games, and what that has cost teams this season". No \
clickbait, no question-only titles.
body: 120-220 words. Two or three findings, each one or two sentences with its number and \
what it's compared with (both sides spelled out), as short paragraphs or a short bullet \
list. Then one short line of opinion (marked as opinion, no numbers in it, one clear \
point) or a real question to the thread. End \
with exactly this line on its own: "Full breakdown, player by player, in my (free) \
newsletter: {LINK}". Nothing else promotional.
chart: which of the column's charts goes with the post (the one that shows the main finding).
comment: for the post-match thread, at most 50 words, no link, no mention of the \
newsletter: the single most telling number with its comparison, in words a casual fan \
gets at a glance (no "metrics", no "lines").
Rules: numbers rounded the way a fan says them (1.19 goals, not 1.187), every number from \
the fact sheet. Never write "elite line" or "worst line" bare; say what it is ("what last \
season's top four managed in a typical win"). Explain xG in passing the first time. Days of \
the week only from "weekday" fields. No emojis, no hashtags, no hype. Nothing from \
"not_measured" as fact. The THE COLUMN block, when given, is the published column: agree \
with it."""


def check_numbers(texts: list[str], facts: dict) -> list[str]:
    allowed = allowed_numbers(facts) | {1, 2, 3, 4, 5}
    bad = sorted({x for t in texts for x in numbers_in(t) if not is_supported(x, allowed)})
    return [f"numbers not in the fact sheet: {', '.join(bad)}"] if bad else []


def check_notes(notes: dict, facts: dict) -> list[str]:
    items = notes.get("notes") if isinstance(notes, dict) else None
    if not items:
        return ["no notes"]
    found = []
    for n in items:
        found.append(n.get("text", ""))
        ch = n.get("chart") or {}
        found += [str(b.get("value")) for b in ch.get("bars", [])]
        if ch.get("reference"):
            found.append(str(ch["reference"].get("value")))
    return check_numbers(found, facts)


def check_reddit(r: dict, facts: dict) -> list[str]:
    if not isinstance(r, dict) or not r.get("body") or not r.get("comment"):
        return ["needs title, body and comment"]
    problems = check_numbers([r.get("title", ""), r["body"], r["comment"]], facts)
    if "{LINK}" not in r["body"]:
        problems.append('the body must end with the newsletter line containing "{LINK}"')
    return problems


def _short(prompt: str, checker, what: str, facts: dict, column: dict | None):
    """One call for a short piece (Notes, Reddit), numbers checked, one retry."""
    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=TIMEOUT_S,
        max_retries=0,
    )
    meta: dict = {"model": settings.llm_model, "calls": 1, "rejected": []}
    user = "HOUSE STYLE:\n" + STYLE + "\n\nFACT SHEET:\n" + json.dumps(facts, ensure_ascii=False)
    if column:
        # Short pieces must give the column's answer, not a new one.
        user += "\n\nTHE COLUMN (give exactly this answer; don't contradict it):\n" + json.dumps(
            column, ensure_ascii=False
        )
    text, msgs = _ask(client, settings.llm_model, prompt, user, 6000, "medium")
    obj = _parse_json(text)
    problems = checker(obj, facts)
    if problems:
        meta["rejected"].append(problems)
        obj = _parse_json(_fix(client, settings.llm_model, msgs, text, problems, 6000))
        meta["calls"] += 1
        if checker(obj, facts):
            raise RuntimeError(f"{what}: {checker(obj, facts)}")
    return obj, meta


def write_notes(facts: dict, column: dict | None = None) -> tuple[dict, dict]:
    """The two Notes for a match."""
    return _short(NOTES, check_notes, "notes", facts, column)


def write_reddit(facts: dict, column: dict | None = None) -> tuple[dict, dict]:
    """A Reddit post (worth reading without the link) and a post-match-thread comment."""
    return _short(REDDIT, check_reddit, "reddit", facts, column)


REDDIT_SUB = "reddevils"


def reddit_submit_url(title: str, body: str, sub: str = REDDIT_SUB) -> str:
    """old.reddit's submit page, pre-filled: open it, review, attach nothing, press submit.
    (old.reddit fills both fields; the new site may fill only the title.)"""
    q = urlencode({"selftext": "true", "title": title, "text": body})
    return f"https://old.reddit.com/r/{sub}/submit?{q}"


def reddit_markdown(r: dict, link: str, images: dict[str, str]) -> str:
    chart = images.get(r.get("chart") or "", "")
    body = r["body"].replace("{LINK}", link)
    return "\n".join(
        [
            "# Reddit for this match",
            "",
            "Post it yourself, after the column is live. Read the sub's rules first; if"
            " blog links aren't allowed as posts, use the comment only.",
            "",
            f"**[Open the post, pre-filled, on Reddit]({reddit_submit_url(r['title'], body)})**"
            " (a text post; review and edit it there, then press submit)",
            "",
            "## Post (r/reddevils, image or text post)",
            "",
            f"**Title:** {r['title']}",
            "",
            f"**Image:** {chart}" if chart else "",
            "",
            body,
            "",
            "## Comment for the post-match thread (no link)",
            "",
            r["comment"],
            "",
        ]
    )


def midway(facts: dict) -> str:
    """When to post the midway Note: noon UK on the day halfway between this match and the
    next one (or three days after, if no next match is known)."""
    played = datetime.fromisoformat(facts["match"]["date"] + "T12:00:00+00:00")
    nxt = (facts.get("next_matches") or [{}])[0].get("kickoff_utc")
    after = datetime.fromisoformat(nxt.replace("Z", "+00:00")) if nxt else None
    if after and after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    day = (played + (after - played) / 2) if after else played + timedelta(days=3)
    uk = datetime.combine(day.date(), dtime(12), tzinfo=ZoneInfo("Europe/London"))
    local = uk.astimezone(ZoneInfo("Europe/Sofia"))
    return f"{uk:%a %d %b}, 12:00 UK ({local:%H:%M} your time)"


def notes_markdown(notes: dict, images: dict[int, str], facts: dict) -> str:
    when = {
        "with the column": "with the column (attach the post when you share it)",
        "midway": midway(facts),
    }
    out = [
        "# Notes for this match",
        "",
        "Two Notes per match: one with the column, one midway.",
        "",
    ]
    for i, n in enumerate(notes["notes"]):
        out += [f"## {when.get(n.get('kind'), n.get('kind', ''))}", "", n.get("text", ""), ""]
        if i in images:
            out += [f"![chart]({images[i]})", ""]
    return "\n".join(out)


def _texts(post: dict) -> list[str]:
    out = [post.get("title", ""), post.get("subtitle", ""), post.get("opener", "")]
    for s in post.get("sections", []):
        out += [s.get("heading", "")]
        out += list(s.get("paragraphs", [])) + list(s.get("bullets", []))
    out += list((post.get("chart_captions") or {}).values())
    return out


def check(post: dict, facts: dict) -> list[str]:
    if not isinstance(post, dict) or not post.get("sections"):
        return ["not an object with sections"]
    allowed = allowed_numbers(facts) | {2026, 2027, 1, 2, 3, 4, 5}
    bad = sorted({n for t in _texts(post) for n in numbers_in(t) if not is_supported(n, allowed)})
    return [f"numbers not in the fact sheet: {', '.join(bad)}"] if bad else []


def _call(client: OpenAI, model: str, msgs: list, max_tokens: int, effort: str) -> str:
    """One LLM call under the gateway's time limit. On a timeout or gateway error, retry
    once with less reasoning (never the identical request); a second failure raises."""
    try:
        text, _ = _complete(client, model, msgs, max_tokens, reasoning_effort=effort)
        return text
    except (TruncatedError, APIStatusError, APIConnectionError):
        # Exactly one more try, never with more reasoning than the first.
        time.sleep(10)
        text, _ = _complete(client, model, msgs, max_tokens, reasoning_effort="low")
        return text


def _ask(client, model, system: str, user: str, max_tokens: int, effort: str):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return _call(client, model, msgs, max_tokens, effort), msgs


def _fix(client, model, msgs, text: str, problems: list[str], max_tokens: int) -> str:
    msgs = msgs + [
        {"role": "assistant", "content": text},
        {
            "role": "user",
            "content": "Fix these problems and return the whole JSON again:\n- "
            + "\n- ".join(problems),
        },
    ]
    return _call(client, model, msgs, max_tokens, "low")


def _checked(
    client, model, system: str, user: str, facts: dict, effort: str, what: str, meta, tokens: int
):
    text, msgs = _ask(client, model, system, user, tokens, effort)
    meta["calls"] += 1
    obj = _parse_json(text)
    problems = check(obj, facts)
    if problems:
        meta["rejected"].append([what] + problems)
        obj = _parse_json(_fix(client, model, msgs, text, problems, tokens))
        meta["calls"] += 1
        if check(obj, facts):
            raise RuntimeError(f"{what} quotes numbers not in the fact sheet: {check(obj, facts)}")
    return obj


def write(facts: dict, team: str) -> tuple[dict, dict, dict]:
    """Plan, then draft, then a critic pass. Returns (plan, post, meta)."""
    if not (settings.llm_base_url and settings.llm_api_key):
        raise RuntimeError("set CORRIDOR_LLM_BASE_URL and CORRIDOR_LLM_API_KEY in backend/.env")
    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=TIMEOUT_S,
        max_retries=0,
    )
    model = settings.llm_model
    meta: dict = {"model": model, "calls": 0, "rejected": []}
    t0 = time.monotonic()
    sheet = "FACT SHEET:\n" + json.dumps(facts, ensure_ascii=False)
    style = "HOUSE STYLE:\n" + STYLE
    # 1. Plan: the only call that reads the whole fact sheet.
    plan = _checked(
        client, model, PLAN, style + "\n\n" + sheet, facts, "medium", "plan", meta, 8000
    )
    # 2. Draft: plan + style only (small and fast).
    user = style + "\n\nPLAN:\n" + json.dumps(plan, ensure_ascii=False)
    post = _checked(client, model, DRAFT, user, facts, "low", "draft", meta, 5000)
    # 3. Critic: claims the data doesn't support become review notes for the editor.
    body = {k: post[k] for k in ("title", "subtitle", "sections")}
    meta["calls"] += 1
    try:
        ctext, _ = _ask(
            client,
            model,
            CRITIC,
            sheet + "\n\nCOLUMN:\n" + json.dumps(body, ensure_ascii=False),
            12000,
            "low",
        )
        flags = [
            {"claim": f.get("claim"), "reason": f.get("reason")}
            for f in (_parse_json(ctext).get("unsupported") or [])
            if isinstance(f, dict)
        ]
        meta["flagged"] = len(flags)
        meta["review"] = flags
        if flags:
            # One revision: fix the flagged sentences; if the result still checks out on
            # numbers, use it and keep the flags as notes on what was changed.
            user = (
                sheet
                + "\n\nCOLUMN:\n"
                + json.dumps(body, ensure_ascii=False)
                + "\n\nFLAGGED:\n"
                + json.dumps(flags, ensure_ascii=False)
            )
            text, _ = _ask(client, model, REVISE, user, 8000, "low")
            meta["calls"] += 1
            revised = _parse_json(text)
            if not check(revised, facts):
                post = revised
                meta["review"] = [
                    {"claim": f["claim"], "reason": "revised — check the new wording"}
                    for f in flags
                ]
    except (TruncatedError, APIStatusError, APIConnectionError, json.JSONDecodeError) as e:
        # A finished draft is never thrown away because the checker failed.
        meta["review"] = [{"claim": "(whole draft)", "reason": f"claim check didn't finish: {e}"}]
    meta["seconds"] = round(time.monotonic() - t0, 1)
    return plan, post, meta


def plan_markdown(plan: dict) -> str:
    out = [
        f"# Plan: {plan.get('title', '')}",
        f"**Angle:** {plan.get('angle', '')}",
        f"**Opener:** {plan.get('opener', '')}",
        "",
    ]
    for s in plan.get("sections", []):
        out += [f"## {s.get('heading', '')}"] + [f"- {b}" for b in s.get("bullets", [])] + [""]
    out += ["**Numbers:** " + ", ".join(str(n) for n in plan.get("numbers_used", []))]
    return "\n".join(out)


def to_markdown(post: dict, images: dict[str, str]) -> str:
    out = [f"# {post['title']}", f"*{post['subtitle']}*", ""]
    order = list(images)
    for i, s in enumerate(post["sections"]):
        out += [f"## {s['heading']}", ""] + [p + "\n" for p in s["paragraphs"]]
        if i < len(order):  # one chart after each of the first sections
            k = order[i]
            out += [
                f"![{post.get('chart_captions', {}).get(k, '')}]({images[k]})",
                f"*{post.get('chart_captions', {}).get(k, '')}*",
                "",
            ]
    out += [
        "Data: FotMob and Understat.",
        "",
        "---",
        "*Drafted from data with an AI assistant and edited by me.*",
    ]
    return "\n".join(out)


def to_html(post: dict, images: dict[str, str]) -> str:
    e = html.escape
    order = list(images)
    review = (post.get("meta") or {}).get("review") or []
    body = []
    if review:
        body.append(
            "<aside class='review'><b>Check before publishing (not part of the post):</b><ul>"
            + "".join(f"<li>“{e(r['claim'] or '')}” — {e(r['reason'] or '')}</li>" for r in review)
            + "</ul></aside>"
        )
    body += [f"<h1>{e(post['title'])}</h1>", f"<p class='sub'>{e(post['subtitle'])}</p>"]
    for i, s in enumerate(post["sections"]):
        body.append(f"<h2>{e(s['heading'])}</h2>")
        body += [f"<p>{e(p)}</p>" for p in s["paragraphs"]]
        if i < len(order):
            k = order[i]
            cap = e(post.get("chart_captions", {}).get(k, ""))
            body.append(
                f"<figure><img src='{images[k]}' alt='{cap}'>"
                f"<figcaption>{cap}</figcaption></figure>"
            )
    body.append("<p>Data: FotMob and Understat.</p>")
    body.append("<hr><p class='sub'>Drafted from data with an AI assistant and edited by me.</p>")
    return (
        "<!doctype html><meta charset='utf-8'><title>" + e(post["title"]) + "</title>"
        "<style>body{max-width:680px;margin:40px auto;padding:0 16px;"
        "font:18px/1.6 Georgia,serif;color:#1d1718}"
        "h1{font:700 2rem/1.15 Helvetica,Arial,sans-serif}"
        "h2{font:700 1.25rem/1.2 Helvetica,Arial,sans-serif;margin-top:2em}"
        ".review{background:#fff3cd;border:1px solid #e3b04f;padding:10px 14px;"
        "font:14px/1.4 Helvetica,Arial,sans-serif}"
        ".sub{color:#6d6264;font-style:italic}img{max-width:100%}"
        "figcaption{color:#6d6264;font-size:.85rem}</style>" + "\n".join(body)
    )


def next_matches(team: str, after: str, season: int, site: Path, n: int = 2) -> list[dict]:
    """The team's next games in any competition after ``after`` (ISO kickoff): league games
    carry our odds; Champions League games carry none (we don't predict them)."""
    out = []
    pred_path = site / "predictions.json"
    if pred_path.exists():
        for f in json.loads(pred_path.read_text())["next_round"]:
            if team not in (f["home"], f["away"]):
                continue
            h = f["home"] == team
            out.append(
                {
                    "competition": "league",
                    "opponent": f["away"] if h else f["home"],
                    "venue": "home" if h else "away",
                    "kickoff_utc": f["kickoff"].replace(" ", "T"),
                    "pct_win": round(100 * f["p"][0 if h else 2]),
                    "pct_draw": round(100 * f["p"][1]),
                    "pct_loss": round(100 * f["p"][2 if h else 0]),
                }
            )
    try:
        ucl = fotmob.league_matches(f"{season}/{season + 1}", fotmob.CHAMPIONS_LEAGUE)
    except Exception:  # noqa: BLE001 — no fixture list → league games only
        ucl = []
    for m in ucl:
        h, a = m["home"]["name"], m["away"]["name"]
        if team not in (h, a) or m["status"].get("finished") or m["status"].get("cancelled"):
            continue
        out.append(
            {
                "competition": "Champions League",
                "opponent": a if h == team else h,
                "venue": "home" if h == team else "away",
                "kickoff_utc": m["status"]["utcTime"],
                "prediction": None,
            }
        )
    out = [m for m in out if m["kickoff_utc"][:16] > after[:16]]
    return sorted(out, key=lambda m: m["kickoff_utc"])[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--league", choices=tuple(LEAGUES), default="pl")
    ap.add_argument(
        "--competition",
        choices=("league", "ucl"),
        default="league",
        help="ucl = the team's Champions League match (no prediction section)",
    )
    ap.add_argument("--team", default=None)
    ap.add_argument("--match", default="latest", help="FotMob match id, or 'latest'")
    ap.add_argument("--no-llm", action="store_true", help="facts and charts only")
    ap.add_argument(
        "--only", choices=("notes", "reddit"), help="only this piece, no column (reruns)"
    )
    ap.add_argument("--link", help="the column's URL for the Reddit post (default: SEO slug)")
    args = ap.parse_args()
    lg = LEAGUES[args.league]
    team = args.team or lg.focus_team
    site = site_dir(args.season, lg)
    league = json.loads((site / "league.json").read_text())
    ucl = args.competition == "ucl"
    prof = league["teams"][team]
    matches = prof["ucl"]["matches"] if ucl else prof["matches"]
    mt = (
        matches[-1]
        if args.match == "latest"
        else next(m for m in matches if m["match_id"] == int(args.match))
    )
    details = fotmob.match_details(mt["match_id"])
    pdir = (
        DATA_DIR / "processed" / str(args.season) / "ucl" if ucl else processed_dir(args.season, lg)
    )
    players = json.loads((pdir / "player_matches.json").read_text())

    pre = None
    log_path = site / "predictions_log.json"
    if not ucl and log_path.exists():
        log = json.loads(log_path.read_text())
        home, away = (team, mt["opponent"]) if mt["is_home"] else (mt["opponent"], team)
        pre = next(
            (
                {
                    "home": e["home"],
                    "away": e["away"],
                    "pct_home_win": round(100 * e["p"][0]),
                    "pct_draw": round(100 * e["p"][1]),
                    "pct_away_win": round(100 * e["p"][2]),
                }
                for e in log.values()
                if e["home"] == home
                and e["away"] == away
                and e["kickoff"][:10] == mt["kickoff_utc"][:10]
            ),
            None,
        )
    nxt = next_matches(team, mt["kickoff_utc"], args.season, site)
    facts = POST.match_facts(
        league, team, mt["match_id"], details, players, pre, nxt, competition=args.competition
    )

    out = (
        DATA_DIR
        / "posts"
        / str(args.season)
        / f"{mt['kickoff_utc'][:10]}-{POST.slug(mt['opponent'])}"
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "facts.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False))
    g = details["general"]
    team_id = g["homeTeam"]["id"] if mt["is_home"] else g["awayTeam"]["id"]
    images = {"lines": "lines.png", "shots": "shots.png", "xg": "xg.png"}
    POST.chart_lines(facts, out / images["lines"])
    POST.chart_shots(details, team_id, team, out / images["shots"])
    POST.chart_xg_race(
        details,
        g["homeTeam"]["id"],
        (g["homeTeam"]["name"], g["awayTeam"]["name"]),
        out / images["xg"],
    )
    print(f"facts + charts → {out}")
    if args.no_llm:
        return
    if not args.only:
        draft_column(facts, team, mt, out, images)
    column = {}
    for name, keys in (("post.json", ("title", "subtitle")), ("plan.json", ("angle",))):
        if (out / name).exists():
            d = json.loads((out / name).read_text())
            column |= {k: d[k] for k in keys if d.get(k)}
    edited = out / "post-edited.md"  # the version actually published, when there is one
    if edited.exists():
        lines = edited.read_text().splitlines()
        column["title"] = lines[0].lstrip("# ").strip()
        column["subtitle"] = lines[2].strip("* ")
    errors = (
        RuntimeError,
        TruncatedError,
        APIStatusError,
        APIConnectionError,
        json.JSONDecodeError,
    )
    if args.only != "reddit":
        try:
            notes, nmeta = write_notes(facts, column or None)
            charts = {}
            for i, n in enumerate(notes["notes"]):
                if (n.get("chart") or {}).get("bars"):
                    charts[i] = f"note-{i + 1}.png"
                    POST.chart_note(n["chart"], out / charts[i])
            (out / "notes.json").write_text(
                json.dumps(notes | {"meta": nmeta}, indent=1, ensure_ascii=False)
            )
            (out / "notes.md").write_text(notes_markdown(notes, charts, facts))
            print(f"notes: {len(notes['notes'])}, {len(charts)} chart(s) → {out / 'notes.md'}")
        except errors as e:
            print(f"note ideas failed: {e}")
    if args.only != "notes":
        try:
            reddit, rmeta = write_reddit(facts, column or None)
            link = args.link or f"https://chomanalysis.substack.com/p/{POST.seo(facts)['slug']}"
            (out / "reddit.json").write_text(
                json.dumps(reddit | {"meta": rmeta}, indent=1, ensure_ascii=False)
            )
            (out / "reddit.md").write_text(reddit_markdown(reddit, link, images))
            print(f"reddit: {reddit['title']} → {out / 'reddit.md'}")
        except errors as e:
            print(f"reddit text failed: {e}")


def draft_column(facts: dict, team: str, mt: dict, out: Path, images: dict) -> None:
    plan, post, meta = write(facts, team)
    post["chart_captions"] = POST.captions(facts)
    (out / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    (out / "plan.md").write_text(plan_markdown(plan))
    post["meta"] = meta | {
        "generated_at": datetime.now(UTC).isoformat(),
        "match_id": mt["match_id"],
    }
    (out / "post.json").write_text(json.dumps(post, indent=1, ensure_ascii=False))
    seo = POST.seo(facts)
    (out / "seo.json").write_text(json.dumps(seo, indent=1, ensure_ascii=False))
    (out / "post.md").write_text(to_markdown(post, images))
    (out / "post.html").write_text(to_html(post, images))
    words = len(re.findall(r"\w+", " ".join(p for s in post["sections"] for p in s["paragraphs"])))
    print(
        f"draft: {post['title']} — {words} words, {meta['calls']} call(s), "
        f"{meta.get('seconds')}s, {len(meta.get('review', []))} review note(s) "
        f"→ {out / 'post.html'}"
    )
    print(f"seo: {seo['title']} | {seo['description']}")


if __name__ == "__main__":
    main()
