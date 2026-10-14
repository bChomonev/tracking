"""Write the analyst's season read from the profile, grounded in its numbers.

    uv run python -m corridor.scripts.analyse [--season 2026] [--model discretestack-max]

Reads data/site/{season}/profile.json, writes analysis.json + facts.json next to it.
"""

import argparse
import json
from datetime import UTC, datetime

from corridor.analyst.facts import build_facts
from corridor.analyst.writer import write_analysis
from corridor.ingest.http import DATA_DIR


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--model", default=None)
    ap.add_argument("--critic-model", default=None, help="defaults to --model")
    ap.add_argument("--no-critic", action="store_true", help="skip the claim-checking pass")
    args = ap.parse_args()

    out = DATA_DIR / "site" / str(args.season)
    facts = build_facts(json.loads((out / "profile.json").read_text()))
    (out / "facts.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False))

    res = write_analysis(
        facts, model=args.model, critic_model=args.critic_model, use_critic=not args.no_critic
    )
    res.analysis["meta"] = {
        "model": res.model,
        "attempts": res.attempts,
        "rejected": res.rejected,
        "dropped_interpretations": res.dropped,
        "seconds": round(res.seconds, 1),
        "generated_at": datetime.now(UTC).isoformat(),
        "matches": facts["record"]["played"],
    }
    (out / "analysis.json").write_text(json.dumps(res.analysis, indent=1, ensure_ascii=False))
    tokens = sum(u.get("total_tokens", 0) for u in res.usage)
    print(f"{res.model}: {res.attempts} attempt(s), {res.seconds:.1f}s, {tokens} tokens")
    for i, problems in enumerate(res.rejected, 1):
        print(f"  attempt {i} rejected: {'; '.join(problems)}")
    for f in res.dropped:
        print(f"  dropped {f['location']}: {f['claim']}")
    print(f"\n{res.analysis['headline']}\n\n{res.analysis['summary']}\n")
    for f in res.analysis["findings"]:
        print(f"[{f['kind']}] {f['title']}\n  {f['text']}")
        if f.get("interpretation"):
            print(f"  ↳ {f['interpretation']}")
    print()
    for p in res.analysis["players"]:
        print(f"[{p['kind']}] {p['name']}: {p['text']}")


if __name__ == "__main__":
    main()
