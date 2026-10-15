"""Ask an OpenAI-compatible LLM to write the season analysis from the fact sheet, and
retry with feedback until every number it quotes is grounded."""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from openai import BadRequestError, OpenAI

from corridor.analyst.validate import check
from corridor.config import settings

SYSTEM_PROMPT = """\
You are the analyst for a website that explains to a Manchester United fan *why* the team \
is performing the way it is. The fan sees almost nothing useful on TV and wants to know: \
are they not running, not pressing, not creating, not finishing, not defending — and who \
is or isn't pulling their weight.

You receive a FACT SHEET (JSON). It is your only source.

Rules:
- Quote numbers exactly as they appear in the fact sheet (you may round them to fewer \
decimals). Never calculate new numbers: no differences, sums, ratios or averages of your \
own. If a comparison is not pre-computed, describe it in words without a number.
- Lead with typical_match (the median match) and league_rank ("20th of 20"), \
league_percentile and league_average for context. Higher percentile is always better. When \
a metric has one_match_effect, say which match distorts the average instead of quoting \
the average as if it were typical.
- Use the best line (each metric's elite_line, and best_line) to say how far United are \
from what last season's top four looked like when winning, and which gaps are biggest. \
Note that United were one of those four, so the line includes their own 2025-26 wins. \
The worst_line is the bottom four in defeat: being at or below it is relegation level.
- Use "proof" to say which lines actually decide matches (and which don't), and what \
happened historically to teams with a match like United's. Quote its percentages exactly; \
say it is association measured on past seasons, not certainty.
- Look for the story *across* metrics, e.g. a team that dominates territory but takes poor \
shots, or concedes few shots but very good ones. Explain what the combination means.
- Keep facts and interpretation apart: "text" contains only what the data shows; \
"interpretation" is your football reading of why (or null). Never present an \
interpretation as fact.
- An interpretation may only build on what the fact sheet contains. Before blaming \
something (shot locations, counter-attacks, set pieces, the press, possession), check the \
metrics and "context" — they often already answer it. Anything listed in "not_measured" \
must not be stated or implied as fact. If the likely explanation is unmeasured, say so \
in one short clause ("the data can't show whether …") — do not list what is missing.
- Mention the small sample if it matters for a conclusion.
- Plain English for a fan, no jargon without a short explanation. No hype, no hedging \
filler.

Return ONLY a JSON object with this shape:
{
  "headline": "one sentence: the single most important thing",
  "summary": "2-3 sentences tying the findings together",
  "findings": [
    {
      "kind": "problem" | "strength" | "watch",
      "title": "short label, max 8 words",
      "text": "1-3 sentences of facts with numbers from the fact sheet",
      "interpretation": "1-2 sentences of football reading, or null",
      "evidence": ["metric key", "..."]
    }
  ],
  "players": [
    {"name": "exact name from the fact sheet", "kind": "positive" | "concern",
     "text": "1-2 sentences"}
  ]
}
Write 4-6 findings (problems first, then strengths, then things to watch) and 3-5 player \
notes. "evidence" must contain metric keys from the fact sheet's metrics[].key."""


CRITIC_PROMPT = """\
You check a football analysis against the FACT SHEET it was written from. Find every \
claim about how the team or a player plays that the fact sheet does not support: it \
describes something the sheet has no data on (anything in "not_measured" counts), \
contradicts a metric or the "context" section, or attributes a cause the numbers do not \
show. A reasonable conclusion that follows from the cited numbers is fine; do not flag \
style, wording or numbers (they are checked separately).

Return ONLY JSON: {"unsupported": [{"location": "...", "claim": "exact quote", \
"reason": "which fact contradicts it, or that it is not measured"}]}
location is one of: "headline", "summary", "finding N text", "finding N interpretation", \
"player NAME" (N counts from 1). Return {"unsupported": []} if everything is supported."""

_INTERP = re.compile(r"^finding (\d+) interpretation$")


class TruncatedError(RuntimeError):
    pass


@dataclass
class AnalystResult:
    analysis: dict
    model: str
    attempts: int
    usage: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    rejected: list[list[str]] = field(default_factory=list)  # problems per failed attempt
    dropped: list[dict] = field(default_factory=list)  # parts removed after the critic


def _parse_json(text: str) -> Any:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _complete(
    client: OpenAI,
    model: str,
    messages: list[dict],
    max_tokens: int = 16000,
    reasoning_effort: str | None = None,
) -> tuple[str, dict]:
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    try:
        resp = client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except BadRequestError:  # endpoint without JSON mode: rely on the prompt
        resp = client.chat.completions.create(**kwargs)
    if not resp.choices:
        raise RuntimeError("LLM returned no choices")
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        raise TruncatedError(f"LLM output was cut off at max_tokens={max_tokens}")
    usage = resp.usage.model_dump() if resp.usage else {}
    return choice.message.content or "", usage


def critique(client: OpenAI, model: str, facts: dict, analysis: dict) -> tuple[list[dict], dict]:
    """Second pass: list claims the fact sheet does not support."""
    body = {k: v for k, v in analysis.items() if k != "meta"}
    messages = [
        {"role": "system", "content": CRITIC_PROMPT},
        {
            "role": "user",
            "content": "FACT SHEET:\n"
            + json.dumps(facts, ensure_ascii=False)
            + "\n\nANALYSIS:\n"
            + json.dumps(body, ensure_ascii=False),
        },
    ]
    # Reasoning models can think past the output limit when checking every claim against a
    # large fact sheet: cap the effort, and drop it further if a run still gets cut off.
    try:
        text, usage = _complete(client, model, messages, 32000, reasoning_effort="medium")
    except TruncatedError:
        text, usage = _complete(client, model, messages, 32000, reasoning_effort="low")
    flags = _parse_json(text).get("unsupported") or []
    return [f for f in flags if isinstance(f, dict) and f.get("claim")], usage


def _drop_flagged(analysis: dict, flags: list[dict]) -> bool:
    """Last-attempt fallback: if every flag sits in an interpretation or a player note,
    remove those parts and return True. Flags in facts, headline or summary can't be
    dropped without leaving a hole, so they fail the run."""
    interps, players = set(), set()
    names = {p.get("name", "").lower() for p in analysis.get("players", [])}
    for f in flags:
        loc = str(f.get("location", "")).strip().lower()
        m = _INTERP.match(loc)
        if m and 1 <= int(m.group(1)) <= len(analysis.get("findings", [])):
            interps.add(int(m.group(1)) - 1)
        elif loc.startswith("player ") and loc[7:] in names:
            players.add(loc[7:])
        else:
            return False
    for i in interps:
        analysis["findings"][i]["interpretation"] = None
    analysis["players"] = [
        p for p in analysis.get("players", []) if p.get("name", "").lower() not in players
    ]
    return True


def write_analysis(
    facts: dict,
    *,
    model: str | None = None,
    critic_model: str | None = None,
    max_attempts: int = 3,
    use_critic: bool = True,
) -> AnalystResult:
    if not (settings.llm_base_url and settings.llm_api_key):
        raise RuntimeError("set CORRIDOR_LLM_BASE_URL and CORRIDOR_LLM_API_KEY in backend/.env")
    model = model or settings.llm_model
    critic_model = critic_model or settings.llm_critic_model or model
    client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=300)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "FACT SHEET:\n" + json.dumps(facts, ensure_ascii=False)},
    ]
    usage: list[dict] = []
    rejected: list[list[str]] = []
    t0 = time.monotonic()
    for attempt in range(1, max_attempts + 1):
        # The model's reasoning counts against max_tokens. At its default effort it often
        # thinks through the whole 32k budget on this fact sheet and returns nothing (75-90 s
        # wasted per call); medium effort writes a full draft in ~40 s, and the number check
        # + critic guard quality. If even that overruns, drop to low.
        try:
            text, u = _complete(client, model, messages, 32000, reasoning_effort="medium")
        except TruncatedError:
            text, u = _complete(client, model, messages, 32000, reasoning_effort="low")
        usage.append(u)
        flags: list[dict] = []
        try:
            analysis = _parse_json(text)
            problems = check(analysis, facts)
        except json.JSONDecodeError as e:
            problems = [f"output was not valid JSON ({e.msg})"]
        if not problems and use_critic:
            flags, u = critique(client, critic_model, facts, analysis)
            usage.append(u)
            problems = [
                f'unsupported claim in {f.get("location")}: "{f["claim"]}" — {f.get("reason", "")}'
                for f in flags
            ]
        if not problems:
            return AnalystResult(analysis, model, attempt, usage, time.monotonic() - t0, rejected)
        if attempt == max_attempts and flags and _drop_flagged(analysis, flags):
            return AnalystResult(
                analysis, model, attempt, usage, time.monotonic() - t0, rejected, flags
            )
        rejected.append(problems)
        messages += [
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": "Fix these problems and return the full JSON again:\n- "
                + "\n- ".join(problems),
            },
        ]
    raise RuntimeError(f"analysis failed checks after {max_attempts} attempts: {problems}")
