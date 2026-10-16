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
from datetime import UTC, datetime
from pathlib import Path

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
4-6 sections, 2-4 bullets each, at most about a dozen numbers in total. Bullets state \
facts from the sheet or clearly-labelled opinion. Nothing from "not_measured" as fact."""

DRAFT = """\
You write the column from an approved PLAN, in the HOUSE STYLE. 600-900 words.
Every sentence must come from a plan bullet, or be clearly marked as my opinion ("I \
think", "to me", "I suspect"). Quote the plan's numbers exactly; add no new numbers and no \
new facts — in particular nothing about how the match flowed (stretches, momentum, who \
was on top when), goalkeepers, tactics or mood unless a plan bullet states it.

Return ONLY JSON:
{"title": "...", "subtitle": "...", "sections": [{"heading": "...", "paragraphs": ["..."]}]}
The first paragraph starts with the plan's opener. Put "Data: FotMob and Understat." as \
the last paragraph on its own."""

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
    out += ["---", "*Drafted from data with an AI assistant and edited by me.*"]
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--league", choices=tuple(LEAGUES), default="pl")
    ap.add_argument("--team", default=None)
    ap.add_argument("--match", default="latest", help="FotMob match id, or 'latest'")
    ap.add_argument("--no-llm", action="store_true", help="facts and charts only")
    args = ap.parse_args()
    lg = LEAGUES[args.league]
    team = args.team or lg.focus_team
    site = site_dir(args.season, lg)
    league = json.loads((site / "league.json").read_text())
    prof = league["teams"][team]
    mt = (
        prof["matches"][-1]
        if args.match == "latest"
        else next(m for m in prof["matches"] if m["match_id"] == int(args.match))
    )
    details = fotmob.match_details(mt["match_id"])
    players = json.loads((processed_dir(args.season, lg) / "player_matches.json").read_text())

    log_path = site / "predictions_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
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
    nxt = None
    pred_path = site / "predictions.json"
    if pred_path.exists():
        f = next(
            (
                x
                for x in json.loads(pred_path.read_text())["next_round"]
                if team in (x["home"], x["away"])
            ),
            None,
        )
        if f:
            h = f["home"] == team
            nxt = {
                "opponent": f["away"] if h else f["home"],
                "venue": "home" if h else "away",
                "kickoff_utc": f["kickoff"],
                "pct_win": round(100 * f["p"][0 if h else 2]),
                "pct_draw": round(100 * f["p"][1]),
                "pct_loss": round(100 * f["p"][2 if h else 0]),
            }
    facts = POST.match_facts(league, team, mt["match_id"], details, players, pre, nxt)

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
    plan, post, meta = write(facts, team)
    post["chart_captions"] = POST.captions(facts)
    (out / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    (out / "plan.md").write_text(plan_markdown(plan))
    post["meta"] = meta | {
        "generated_at": datetime.now(UTC).isoformat(),
        "match_id": mt["match_id"],
    }
    (out / "post.json").write_text(json.dumps(post, indent=1, ensure_ascii=False))
    (out / "post.md").write_text(to_markdown(post, images))
    (out / "post.html").write_text(to_html(post, images))
    words = len(re.findall(r"\w+", " ".join(p for s in post["sections"] for p in s["paragraphs"])))
    print(
        f"draft: {post['title']} — {words} words, {meta['calls']} call(s), "
        f"{meta.get('seconds')}s, {len(meta.get('review', []))} review note(s) "
        f"→ {out / 'post.html'}"
    )


if __name__ == "__main__":
    main()
