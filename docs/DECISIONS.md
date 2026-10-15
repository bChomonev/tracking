# Decision Log

TDP-001 and ARCHITECTURE.md are a **compass, not a contract**. When we deviate from them,
fill a gap, or resolve a contradiction between them, it goes here — newest first. If a
decision supersedes a doc statement, the doc is updated or the entry says so.

Format: **D-NNN — Title** · date · status (`accepted` / `revisit` / `superseded by D-XXX`)

---

## D-027 — Scoreline model for goal lines · 2026-10-15 · accepted (1X2: revisit)
Poisson goals per side (scikit-learn PoissonRegressor on the same pre-match ratings:
own npxG / goals for, opponent npxGA / goals against) with a Dixon–Coles low-score
correction → a scoreline matrix → most likely scores, over 1.5 / 2.5 / 3.5, both teams to
score, clean sheets. Raw rates were over-confident (74% "over 2.5" happened 62%), so rates
are shrunk towards the league mean in log space; the factor 0.7 was chosen on 2016-17…
2019-20. Held-out 2020-21…now: over 2.5 Brier 0.2435 vs 0.2476 base rate, bookmakers
0.2414; BTTS 0.2476 vs 0.2490. **Win/draw/loss stays with the logistic model**: it won on
the tuning seasons (RPS 0.1917 vs 0.1923) although the unshrunk goals model was better on
the held-out ones (0.2025 vs 0.2046) — switching on held-out evidence would be choosing by
the test set; revisit with a fresh tuning protocol. **Alignment (same day, after the user
spotted it):** scorelines first came from the goals model alone, so Leeds–United showed
Leeds favourites (45/25/30, with team news) but 1–2 above 2–1. Now the goals model sets the
expected *total*, and the split between the sides is solved so the matrix's home-minus-away
win chance equals the published prediction (team news included). Held-out: over 2.5
unchanged (0.2435), 1X2 0.2054 → 0.2046, exact-score log loss 2.9862 → 2.9855. The page
also explains why the single likeliest score can be a draw while one side is favourite. Matching only the
home-minus-away gap left draws up to ~3 points off, so the home-win, draw and away-win
scorelines are then each rescaled to sum exactly to the published chances (`reconcile`);
held-out over 2.5 0.2434, exact-score log loss 2.9864. Applies to every fixture.

## D-026 — Team news in the prediction (one parameter) · 2026-10-15 · accepted (watch)
`corridor.absences`: FotMob lists each side's unavailable players on every match page, so
the cached pages give 820 past PL matches (2024-25 → now) of team news. Each absent
player is weighted by his share of the team's minutes and of its chance creation (npxG +
xA), counted only over earlier matches (last season at half weight). Tests: re-fitting a
stacked model on one season *hurt* (overfit), so the adjustment is a single parameter —
home-win odds × exp(k·d), away-win odds × exp(−k·d), d = away minus home share of usual
minutes missing. k fitted separately on 2024-25 (1.74) and 2025-26 (1.90) → 1.8. Out of
sample the gain is small and not significant (+0.0007 and +0.0022 RPS, CIs include 0;
−0.0026 on this season's 60), right direction in the 63 big-gap matches (home side
missing much more: base 38%, adjusted 30%, actual 20%). Adopted because the direction is
stable and both versions are logged: the running record shows RPS with and without team
news, so it can be dropped if it doesn't pay. Using output share or both shares overfit.

## D-025 — Who takes the shots (player shot quality) · 2026-10-15 · accepted
Per player, from the shot map: non-penalty shots, npxG per shot vs the league average for
his role, distance, outside-box / blocked / headed shares, and **npxG wasted** = shots ×
role-average quality − actual npxG; summed it splits the team's shot-quality gap by
player (United: 0.45 per match, most in the league — Cunha +1.49, Rashford +0.64, the
centre-backs and Dalot shooting from range; Mbeumo −1.04). Defending can't be split the
same way (no per-player attribution of chances allowed), only "errors leading to a goal"
is shown. The parser now records per-player shot detail and uses the match's own team
names — FotMob's player blocks said "Bournemouth" / "Brighton and Hove Albion", which had
silently emptied those two teams' player tables and team-news shares since D-022.

## D-024 — Stage 5: match previews (team news, line-ups, shooters, corners) · 2026-10-15 · accepted
Clicking a next-round fixture opens `#match/<id>`: the prediction, **team news** (FotMob's
pre-match "unavailable" list: type, expected return, the player's minutes and share of the
team's npxG + xA this season), **line-ups** (FotMob's last starting XI until the official
one is out, ~1 h before kickoff; players now out are struck through), **likely shooters**
and **corners**. Built by `scripts/previews.py` after `predictions` (one FotMob request per
fixture per run). The parser now records team corners and per-player non-penalty shots,
shots on target, npxG (from the shot map), penalties and non-penalty goals.
**Shooters:** shots and npxG per 90 this season + last (half weight), shrunk towards the
role average with 270 minutes of prior, × usual minutes when starting × the opponent's
shots / npxG conceded relative to the league; Poisson for P(≥1 shot) and P(non-pen goal),
"if he starts". Walk-forward on 2025-26 (7,600 starts): Brier 0.207 vs 0.220 for a role
average; goal chances calibrated. **Corners:** opponent-adjusted rolling corners won /
conceded (30-match half-life, chosen on 2025-26). Honest finding: a side's corners are
predictable (MAE 2.07 vs 2.15; the expected "more corners" side wins them 62%), the match
**total is not** (correlation 0.06; worse than the league average), so totals use the
league average. **Absences are shown, not used** in the win/draw/loss model: there is no
injury history to test an adjustment against; shooter lists drop players who are out.

## D-023 — Stage 4: pre-match predictions, honestly tested · 2026-10-15 · accepted
**Ratings** (`corridor.predict`): every team carries exponentially weighted Understat
non-penalty xG for/against, goals for/against and the share of the 5 core elite / worst
lines reached (lines from the previous season). Each match is **opponent-adjusted** before
it updates a rating (1.5 npxG against a side that concedes 2.0 counts as below par).
Ratings update only *after* a match; summer carry-over and a promoted-team prior (the
relegated teams' ratings) handle new seasons. **Model:** multinomial logistic regression
(scikit-learn, L2) on rating differences → P(home/draw/away).
**Protocol:** settings (half-life, carry-over, opponent adjustment, feature set, L2) tuned
on 2016-17…2019-20 only, then **frozen** (`PARAMS` in `scripts/predictions.py`: 24-match
half-life, full carry-over, opponent-adjusted, xG+goals+lines, C=0.05). Held-out
2020-21…now, each season trained only on earlier ones: **RPS 0.205** vs base rates 0.234
and bookmakers 0.198 (pre-match average) / 0.197 (closing); favourite won 53% vs the
market's 54%. Calibrated, slightly over-confident above ~65%. The line features add almost
nothing beyond xG + goals (honest result, kept because tuning chose them). A wider grid
fit the tuning seasons better but not the held-out ones, so we stopped tuning there.
**Live:** after every build, the next round is predicted, the rest of the season simulated
(20,000 runs from fixed ratings: projected points, title / top-4 / relegation odds), and
each prediction is **frozen at its last pre-kickoff version** in `predictions_log.json` and
scored after the match against the market. Known limit: ratings move slowly, so early in a
season they lean on last season (e.g. United 41% to win at Leeds after a poor start).
Odds come from football-data.co.uk and are used only as a benchmark (DATA_SOURCES.md).

## D-022 — Premier League overview + a breakdown for every team · 2026-10-15 · accepted
The site now opens on a Premier League overview; every team gets the same breakdown United
has (focus tiers, proof, match table, stacks, players, UCL tab if they play in it). The
**analyst stays United-only** (the user's team; it costs ~3 min / ~200k tokens a run).
`united_profile` builds all 20 teams in one pass (lines and proof computed once, placed per
team) and writes `league.json` (all teams + overview table) next to `profile.json` (focus
team + shared proof, still the analyst's input). Understat rows are joined to FotMob
team-matches by day + score + Understat PPDA + deep completions for/against — score and
deep completions alone mixed up two 2-2 draws on the same day.
**Overview:** a table sorted by any column — points, **deserved points**, points minus
deserved, xG, the 7 decisive metrics (elite / between / relegation level), elite and danger
scores, stack percentiles, form — plus an elite-vs-danger scatter and a points-vs-
performance chart. **Deserved points** per match = mean of 3·W + D over the historical
bins for the match's elite score and its danger score (FotMob weighted record); it
describes performances, it is not yet a prediction. Hash routing (`#team/<slug>`) keeps it
one static page (~1.5 MB). **Automation:** `update` now rebuilds after any finished PL
match and any UCL match involving a PL team, not just United's.

## D-021 — Page refocused on what decides matches; impact-weighted lines · 2026-10-15 · accepted
The page listed 29 metrics with equal weight, so United's strengths (territory, PPDA,
passes into the final third) visually balanced weaknesses that matter far more. Each
metric now gets an **impact** = mean of its best-line lift and worst-line lift on the
FotMob out-of-sample record, and a tier: **decides matches** ≥ 0.20, **helps a little**
0.10–0.20, **doesn't decide matches** < 0.10 (provisional if < 300 tested team-matches,
i.e. running metrics). Outcome-linked metrics and line-breaking passes stay untiered.
**Weighted score:** share of lines reached with each line weighted by its lift (floored
at 0). Checked walk-forward — weights learned only from earlier seasons: Understat AUC
for wins 0.675 → 0.714 (7,720 team-matches, 2016-17→now), losses 0.705 → 0.738; FotMob
this season 0.64 → 0.73 (120). Top-group win rate is unchanged (85%), so the 90% target
is still not met. FotMob weights/bins used to place United's matches come from the full
record (in-sample for the bins; the walk-forward test is what justifies weighting).
**Page order:** record → What decides matches (tiers, each metric on a worst→elite gauge;
the no-effect tier collapsed) → analyst → How we know (proof) → match table (elite/danger
scores + the decisive metrics, shaded by line) → every metric by stack (sorted by impact,
tagged) → players. The rule-based percentile verdict and the separate "Against the
lines" section are gone. The analyst gets `what_decides_matches` and a per-metric
`decides_matches`, and is told to build the read around the decisive tier.

## D-020 — Stage 3: worst line + out-of-sample proof · 2026-10-15 · accepted
**Worst line** mirrors D-019: median of every metric over the previous season's bottom
four's league *defeats*, minus defeats where they were down to 10 men before the 70th
minute (2025-26: Spurs, West Ham, Burnley, Wolves; 76 defeats, 8 excluded). Hitting it =
relegation level. `best_line.py` is now generic (`side="best"|"worst"`, any rows/metrics).
**Proof** (`corridor.proof`): for each pair of consecutive seasons, lines from season N are
tested on *every* team-match of N+1 (never on the games that built them). Per match: share
of lines reached / sunk to → outcome rates by share bin, the share needed for the 90% W /
85% L targets (min 30 matches), and each line's lift (win rate when reached − when not).
Two datasets, never mixed: Understat 2014-15→now on 5 core metrics (8,480 team-matches)
and FotMob 2024-25→now on the profile metrics (880). Goals prevented, finishing (xGOT−xG)
and big chances missed are excluded from the proof — they partly contain the result.
Running lines can only be tested on 2026-27 (no tracking before Dec 2025).
**Findings (honest):** the 90% win target is *not* met: all 5 core best lines → 85% won
(164). The 85% loss target *is* met: all 5 core worst lines → 85.2% lost (378). Lines differ
hugely in what they predict: chance quality for/against, big chances, shot quality and
distance vs opponent separate wins; territory, passes into the final third, PPDA, sprints
and recoveries barely do. Caveat on the page: whole-match numbers are partly shaped by the
score (game state), so this is association, not cause. This replaces TDP's single npxGD
corridor (D-009) as the user-facing proof; the pgvector engine stays unused for now.
Possible next step: weight lines by out-of-sample lift (select on early seasons, test on
later ones) instead of counting them equally.

## D-019 — Stage 2 best line: last season's top-4 wins, median per metric · 2026-10-15 · accepted
Chosen with the user. **Elite** = the previous season's final top four (2025-26: Arsenal,
Man City, Man United, Villa — United's own 3rd place included). **Best games** = their
league wins, minus wins where the opponent was sent off before the 70th minute (11 v 10
for 20+ min inflates possession/territory; 3 excluded). **Line** = median of each metric over
those wins; the middle half (p25–p75) is the "elite range". Fixed for the season, rebuilt
each summer from `data/processed/{season-1}` (needs a one-off `build_season --season
<prev>`, ~10 min). "Reached" = at least as good as the median; gaps are also expressed in
elite-range units so metrics with different scales can be ranked. Running metrics rest on
the ~57 wins with tracking (FotMob tracking starts Dec 2025).
**Cross-season guard:** if a metric's league-wide mean moved > 0.5 SD between seasons, the
provider changed its definition and the metric gets no line — FotMob's line-breaking
passes went from a median of 52 to 93.5 (+1.9 SD). PL only: the UCL has different
providers and no previous-season pool. Supersedes TDP's 90%-win cohort as the *displayed*
line for now; the empirical 90%-win proof stays for stage 3.

## D-018 — Post-match updates: local launchd + a background Claude session publishes · 2026-10-15 · accepted
`corridor.scripts.update` runs twice a day (10:31, 14:31 local — when the Mac is awake) from
a user launchd agent (`ops/launchd/`). It refreshes the PL + UCL fixture lists and only
rebuilds when United have a new finished match whose data is in: tried from 3 h (PL) / 12 h
(UCL) after kickoff, and it checks the slow sources actually have the match (Understat PPDA,
UEFA tracking ~17 h) before the expensive steps, waiting up to 72 h. A late UCL match
usually lands the next day at 14:31 or the morning after. Then build_season (pl, ucl) → united_profile
→ analyse (one retry; on a second failure the stale read is moved aside so the page never
shows text about older numbers) → build_site. Publishing needs Claude's Artifact tool, which
`claude -p` lacks but a `claude --bg` session has: the script starts one with a narrow
"publish this file to this URL, nothing else" prompt and removes the previous run's
session. Rejected: a cloud routine (scraped data + LLM key would have to live in the cloud,
and every run would re-scrape from scratch) and in-session cron (dies with the session,
7-day cap). Trade-off: the Mac must be on; missed runs fire on wake. State:
`data/site/{season}/update_state.json`; logs: `data/logs/update.log`.

## D-017 — Champions League: FotMob events + UEFA tracking, own pool · 2026-10-15 · accepted
UCL matches are built separately (`build_season --competition ucl` → `data/processed/{season}/ucl/`).
Event stats and the shot map come from FotMob (league 42, same parser as the PL); physical
data comes from UEFA's match centre, joined on date + score + team-name similarity. United
are ranked only against the other UCL team-matches (36 teams), never against PL numbers:
different tracking providers measure distance and sprints differently. Metrics a
competition lacks are skipped (no PPDA / deep completions: Understat covers leagues only).
UCL-only metrics: running without the ball, scaled to 50% opponent possession
(`km_oop × 50 / opp_possession%`, so possession neither flatters nor punishes it), and
high-intensity runs. UCL players and a UCL analyst read are not done yet (UEFA player
stats need a name join; 2 matches is too few for a written read).

## D-016 — Rank on the typical (median) match; flag one-match skew · 2026-10-15 · accepted
With 6 matches one freak game carries a mean: United's npxG was 5th on average but 13th on
the median, because of 3.99 vs Ipswich. 84 of 580 team-metric ranks moved ≥5 places
between mean and median. Every team's season value is now its **median match**, and rank,
percentile, league average/best/worst and stack scores use it. The mean is kept as
`season_average` with its own rank. `skew` finds the match whose removal moves the mean
most and flags the metric when dropping it moves the average-based rank by ≥ max(3,
teams/5) places (only with ≥4 matches). The page tags such metrics "skewed" and names the
match; the analyst must name it when it quotes the average. Considered: trimmed mean
(similar ranks, harder to explain) and pooled totals (worse: weights the big game more).

## D-015 — Close the analyst's guessing gaps: shot map, context facts, claim critic · 2026-10-14 · accepted
The number check (D-014) let qualitative guesses through ("shots from distance", "possession
teams run less", "presses only the big sides"). Three fixes:
1. **More data.** FotMob's `shotmap` is parsed per team (penalties and own goals excluded,
   105 x 68 m pitch): shot distance, outside-box share, blocked share, set-piece and
   fast-break npxG, goals by type. Plus big chances missed, shots conceded and sprints vs
   opponent. 9 new ranked metrics (28 in total).
2. **Context facts** pre-computed in `profile._context`: goals by type, possession vs
   distance correlation across all team-matches (and distance among ≥55% possession
   teams), PPDA vs top-half / bottom-half opponents, opponent league position per match.
   A `not_measured` list (shape, line height, press triggers, off-ball runs, chance
   creation, errors, morale, player shooting) tells the model what it must not assert.
3. **Critic pass.** After the number check passes, a second LLM call lists claims the fact
   sheet does not support; they go back to the writer as problems. On the last attempt,
   flagged interpretations / player notes are dropped (logged in `meta`) rather than
   failing; flags in facts, headline or summary still fail the run.
Cost: the critic roughly triples a run (~4 min, ~170k tokens with `discretestack-max`).
`--critic-model discretestack-fast` is ~10 s per check but missed some claims in testing.

## D-014 — AI analyst: code computes, LLM writes, code checks · 2026-10-14 · accepted
The written season read is generated at build time (once per update, not per visitor) by an
OpenAI-compatible LLM (user's own DiscreteStack endpoint, `discretestack-max`; configured in
gitignored `backend/.env`). `analyst/facts.py` builds a fact sheet with every quotable number
pre-computed and pre-rounded (incl. comparisons like "out-run in 5 of 6"); the model may not
do arithmetic. `analyst/validate.py` rejects output containing any number not in the fact
sheet (at the quoted precision), unknown metric keys or players; the writer retries with the
problems as feedback (max 3). Facts and interpretation are separate fields and the page labels
interpretation as "Reading". An interactive "ask the analyst" box is deferred: it needs a
server so the key never reaches the browser.

## D-013 — Stage 1 is a United-only static page from FotMob + Understat · 2026-10-14 · accepted
After a scope reset with the user: the goal is answering "why are United bad?", not a SaaS.
Season profile ranks United against all 20 PL teams per metric; players are compared within
their real role (CB/FB/CM/AM/W/ST from FotMob's line-up grid). Scraped data never enters git
(public repo). The pgvector corridor engine (D-001–D-011) is kept for the later "proof" stage.

## D-012 — Synthetic-first data strategy · 2026-10-14 · accepted
Free sources can't supply most of the 12 dimensions (physical tracking, line breaks, xGOT,
PSxG, box touches). The whole engine is built and tested on a seeded synthetic generator
(`corridor.synthetic`) whose paired metrics mirror real constraints (A's npxG conceded = B's
npxG created, field tilt sums to 100, goals ~ Poisson(post-shot xG)). Real providers come
later behind an adapter interface. **Revisit** when picking a data provider (WP1.2/1.3).

## D-011 — Recalibration re-vectorizes every stored row · 2026-10-14 · accepted
Z-scores depend on the benchmark window's μ/σ, so vectors computed under different
corridor versions are not comparable. `calibrate()` writes a new `benchmark_corridors` row,
deactivates the previous one, and rewrites `stats_vector` + scores for **all** rows in the
same transaction (~9 s for 19k rows). Simpler than per-version vector tables; fine until
row counts are in the millions.

## D-010 — Twin search excludes the audited match and the future · 2026-10-14 · accepted
`find_twins` filters `kickoff_utc < audited kickoff` and `match_id <> audited match` (which
removes the opponent's mirrored row too). Uses pgvector ≥ 0.8 `hnsw.iterative_scan =
strict_order` so filters can't starve the k = 50 result. `kickoff_utc` is denormalized onto
`team_match_performances` for this.

## D-009 — Corridor cohorts via logistic fit on npxGD · 2026-10-14 · accepted · revisit
TDP's definition ("npxGD ≥ +1.60 … where teams win ≥ 90%") is circular. We fit
P(win | npxGD) and P(loss | npxGD) with 1-D logistic regressions and take the widest tail
cohort whose *fitted* mean outcome rate meets the target (90% W / 85% L); centroid = mean
vector of that cohort, floor of 30 rows. An earlier "scan down from the top" approach was
rejected: one result in the thin tail broke the scan and 365-day windows were unsolvable.
"Positive stack alignment" from TDP is not applied yet.
**Open issue:** on a 365-day window the 90% win cohort is only ~1% of performances (~30
rows). Options: longer window for the lines (keep 365 d for μ/σ), lower target, or accept.

## D-008 — Similarity % is relative to corridor width · 2026-10-14 · accepted
`similarity_pct = 100 · max(0, 1 − d / ‖v_best − v_worst‖)`. 0 distance → 100%, a twin as
far away as the whole corridor → 0%. TDP showed values but never defined the formula.

## D-007 — Badge rules and precedence · 2026-10-14 · accepted
Evaluated in order, first match wins:
1. `MIRAGE_WIN` — points = 3 and (twin win% ≤ 22 or ≥ 2 vetoes)
2. `UNLUCKY_LOSS` — points = 0 and twin win% ≥ 75
3. `ELITE_90_STANDARD` — C ≥ 82, twin win% ≥ 88, 0 vetoes
4. `SYSTEMIC_COLLAPSE` — C ≤ 20 or ≥ 2 vetoes *(TDP named this badge but never defined it)*
5. `MID_TABLE_STANDARD` — otherwise

Veto threshold: stack score **≤ 20.0** (TDP), not < 18.0 (ARCHITECTURE).
Veto flag names derive from the stack score column: `STACK_01_WORK_RATE_VETO`, etc.

## D-006 — Feature weights: TDP values, single source in code · 2026-10-14 · accepted
The two docs disagree on 5 of 12 weights. We use TDP's (1.8 / 1.4 / 1.2 / 1.0 tiers). The
only definition lives in `corridor/engine/metrics.py`; the active weights are also
snapshotted into each `benchmark_corridors.metric_weights` row. Clip ±4.5 applies *after*
weighting (per TDP formula) — note this means a 1.8-weight metric clips at |z| = 2.5.
**Revisit** once we can tune against real outcomes.

## D-005 — Player effort: re-ranked composite, no gap band · 2026-10-14 · accepted
Composite = 50% mean physical percentile + 50% mean event percentile, then **re-ranked**
within the positional cohort (averaging percentiles compresses toward 50, so the raw
average almost never reaches 85). Bands: `WORKHORSE_ELITE` ≥ 85, `PASSENGER_ALERT` < 15,
`STANDARD_SHIFT` otherwise (closes TDP's undefined 15–20 gap). Players without physical
tracking are scored on event work rate alone. GK excluded. `progression_corridor_score`
dropped from the schema (never defined). `final_third_regains_per_90` is stored but not
scored.

## D-004 — Missing metrics impute to the benchmark mean · 2026-10-14 · accepted · revisit
Nullable physical columns; a missing metric gets z = 0 so it neither helps nor hurts
similarity. Revisit if most rows lack physical data (distance then concentrates on 10 dims).

## D-003 — Merged schema · 2026-10-14 · accepted
Base: TDP §5 (12 explicit rate columns, `competition_code`, `audit_status`, `league_code`,
`elo_rating`). Added from ARCHITECTURE: `raw_metrics JSONB` (provenance). Added new:
`goals_for/against`, denormalized `kickoff_utc`, `venue`, corridor `window_start/end_utc`
and `calibration JSONB`, snapshot `schema_version`. Scores/vector nullable until a corridor
exists. `audit_status` gains `HISTORICAL` for backfilled matches. No table partitioning
yet (ADR-07): the player table has no vector index, and row counts are small.

## D-002 — Plain SQLAlchemy 2.0 + Alembic (no SQLModel), sync psycopg 3 · 2026-10-14 · accepted
SQLModel adds little over typed SQLAlchemy 2.0 here and is awkward with pgvector types.
The write path is a short batch job, so sync psycopg 3 is enough. Alembic migrations are
the DDL source of truth; `alembic check` must report no drift against the models.

## D-001 — Repo layout: `backend/` uv project with `src/corridor` package · 2026-10-14 · accepted
Python project lives in `backend/` (own `pyproject.toml`, `uv.lock`, `alembic.ini`), with
`engine/` (pure NumPy, no DB), `db/`, `synthetic/`, `scripts/`. `frontend/` (Next.js) will
sit alongside. Local Postgres on port **5433** to avoid clashing with a host Postgres.
LLM autopsy will use a current Claude model, not the docs' Claude 3.5 Sonnet / GPT-4o.
