# Decision Log

TDP-001 and ARCHITECTURE.md are a **compass, not a contract**. When we deviate from them,
fill a gap, or resolve a contradiction between them, it goes here — newest first. If a
decision supersedes a doc statement, the doc is updated or the entry says so.

Format: **D-NNN — Title** · date · status (`accepted` / `revisit` / `superseded by D-XXX`)

---

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
