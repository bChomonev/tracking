---
name: united-post
description: Draft or edit a post-match Substack column about Manchester United in the house style (first-person fan, honest and dry, data-backed). Use when asked to write, plan, rewrite or polish a post-match post, or to apply the house style to a draft.
---

# Post-match column (house style)

The style guide is `backend/src/corridor/prompts/house_style.md` — read it first and follow
it exactly. The automatic pipeline (`uv run python -m corridor.scripts.post`, D-034) uses the
same file, so hand-written and generated drafts sound the same.

## Inputs
For a match, `data/posts/{season}/{date}-{opponent}/` holds:
- `facts.json` — the only source of facts and numbers (lines, elite/danger scores, players,
  events, prediction before kickoff, next match, `not_measured`);
- `lines.png`, `shots.png`, `xg.png` — the three charts;
- `plan.md` / `post.md` / `post.html` if the pipeline already drafted it.
If the folder doesn't exist, run `uv run python -m corridor.scripts.post --match <fotmob id>
--no-llm` from `backend/` to build the facts and charts first.

## Steps
1. **Plan first.** Write the angle (one sentence), title, subtitle, opener, 4–6 sections as
   bullets, and the list of numbers you'll quote. Show the plan to the user before writing
   prose unless they asked for the full draft.
2. **Draft from the plan** in the house style, 600–900 words, charts after sections 1–3.
3. **Check every number** against `facts.json` (exact or rounded; never computed). Anything
   in `not_measured` is opinion at most, and labelled as such.
4. Save as `post.md` in the match folder (keep any pipeline version as `post.pipeline.md`).

Never publish anything; the user pastes the final version into Substack.
