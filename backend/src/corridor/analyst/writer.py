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
- Use league_rank ("20th of 20"), league_percentile and league_average to give context. \
Higher percentile is always better.
- Look for the story *across* metrics, e.g. a team that dominates territory but takes poor \
shots, or concedes few shots but very good ones. Explain what the combination means.
- Keep facts and interpretation apart: "text" contains only what the data shows; \
"interpretation" is your football reading of why (or null). Never present an \
interpretation as fact.
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


@dataclass
class AnalystResult:
    analysis: dict
    model: str
    attempts: int
    usage: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    rejected: list[list[str]] = field(default_factory=list)  # problems per failed attempt


def _parse_json(text: str) -> Any:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _complete(client: OpenAI, model: str, messages: list[dict]) -> tuple[str, dict]:
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": 16000}
    try:
        resp = client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except BadRequestError:  # endpoint without JSON mode: rely on the prompt
        resp = client.chat.completions.create(**kwargs)
    if not resp.choices:
        raise RuntimeError("LLM returned no choices")
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError("LLM output was cut off (max_tokens)")
    usage = resp.usage.model_dump() if resp.usage else {}
    return choice.message.content or "", usage


def write_analysis(
    facts: dict, *, model: str | None = None, max_attempts: int = 3
) -> AnalystResult:
    if not (settings.llm_base_url and settings.llm_api_key):
        raise RuntimeError("set CORRIDOR_LLM_BASE_URL and CORRIDOR_LLM_API_KEY in backend/.env")
    model = model or settings.llm_model
    client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=300)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "FACT SHEET:\n" + json.dumps(facts, ensure_ascii=False)},
    ]
    usage: list[dict] = []
    rejected: list[list[str]] = []
    t0 = time.monotonic()
    for attempt in range(1, max_attempts + 1):
        text, u = _complete(client, model, messages)
        usage.append(u)
        try:
            analysis = _parse_json(text)
            problems = check(analysis, facts)
        except json.JSONDecodeError as e:
            problems = [f"output was not valid JSON ({e.msg})"]
        if not problems:
            return AnalystResult(analysis, model, attempt, usage, time.monotonic() - t0, rejected)
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
