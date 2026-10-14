"""Grounding checks for the analyst's output.

Every number in the written text must exist in the fact sheet at the precision it is
quoted (0.074 may be written 0.07; 112.105 may be written 112). Signs are ignored so
"out-run by 1.8 km" matches a stored -1.8. Evidence keys must name real metrics.
"""

import json
import re
from typing import Any

_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def numbers_in(text: str) -> list[str]:
    return _NUM.findall(text)


def allowed_numbers(facts: dict) -> set[float]:
    return {abs(float(n)) for n in numbers_in(json.dumps(facts))}


def is_supported(token: str, allowed: set[float]) -> bool:
    value = abs(float(token))
    decimals = len(token.split(".")[1]) if "." in token else 0
    return any(round(a, decimals) == value for a in allowed)


def _texts(analysis: dict) -> list[str]:
    out = [analysis.get("headline", ""), analysis.get("summary", "")]
    for f in analysis.get("findings", []):
        out += [f.get("title", ""), f.get("text", ""), f.get("interpretation") or ""]
    for p in analysis.get("players", []):
        out += [p.get("text", "")]
    return out


def check(analysis: Any, facts: dict) -> list[str]:
    """Return a list of problems; empty means the analysis is grounded and well-formed."""
    if not isinstance(analysis, dict):
        return ["output is not a JSON object"]
    problems = []
    for field in ("headline", "summary", "findings", "players"):
        if not analysis.get(field):
            problems.append(f"missing field: {field}")

    metric_keys = {m["key"] for m in facts["metrics"]}
    player_names = {p["name"] for p in facts["players"]}
    for i, f in enumerate(analysis.get("findings", [])):
        if f.get("kind") not in ("strength", "problem", "watch"):
            problems.append(f"finding {i + 1}: kind must be strength, problem or watch")
        bad = [k for k in f.get("evidence", []) if k not in metric_keys]
        if bad or not f.get("evidence"):
            problems.append(f"finding {i + 1}: evidence must list metric keys, got {bad or []}")
    for p in analysis.get("players", []):
        if p.get("name") not in player_names:
            problems.append(f"unknown player: {p.get('name')!r}")

    allowed = allowed_numbers(facts)
    unsupported = sorted(
        {t for text in _texts(analysis) for t in numbers_in(text) if not is_supported(t, allowed)}
    )
    if unsupported:
        problems.append(
            "numbers not in the fact sheet (do not calculate new numbers; quote existing "
            f"ones or rephrase without numbers): {', '.join(unsupported)}"
        )
    return problems
