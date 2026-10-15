# Corridor Engine

Football Performance Corridor & Effort Intelligence Platform. After every match, a batch job
scores each team's 12-dimension performance profile between an empirical **90% Win Ceiling** and
**85% Loss Floor**, finds its 50 closest historical twins with pgvector, audits player effort,
and publishes an immutable static JSON audit to the edge.

- Product & math: [`docs/TDP-001-v1.1.md`](docs/TDP-001-v1.1.md)
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Decisions log: [`docs/DECISIONS.md`](docs/DECISIONS.md)

## United season page (stage 1)

```bash
cd backend
uv run python -m corridor.scripts.build_season    # fetch PL 2026-27 from FotMob + Understat (cached in data/raw)
uv run python -m corridor.scripts.build_season --competition ucl  # UCL: FotMob events + UEFA running data
uv run python -m corridor.scripts.build_season --season 2025  # once per season: last season = best/worst lines
uv run python -m corridor.scripts.build_season --season 2024  # once: the season before, for the proof
uv run python -m corridor.scripts.united_profile  # rank United vs the league + lines + historical proof
uv run python -m corridor.scripts.analyse         # LLM analyst writes + a critic checks the season read (needs backend/.env, ~4 min)
uv run python -m corridor.scripts.build_site      # render data/site/2026/index.html from web/united.html
```

**Automatic updates after each match:** `./ops/launchd/install.sh` installs a launchd job
(10:31 and 14:31) that runs `corridor.scripts.update --publish`: it rebuilds only
when United have a new finished match whose data is ready, then a background Claude Code
session republishes the artifact. Try it by hand with `uv run python -m
corridor.scripts.update --check`. Log: `data/logs/update.log`.

`data/` is gitignored: this repo is public and the sources' terms forbid republishing
their data. See [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

## Engine quickstart (later stages)

```bash
docker compose up -d                 # Postgres 16 + pgvector on :5433
cd backend
uv sync
uv run alembic upgrade head
uv run python -m corridor.scripts.seed_synthetic
uv run pytest
```

## Status

| Work package | State |
| --- | --- |
| WP1.1 Postgres + pgvector schema, HNSW index | ✅ |
| WP1.2 Historical backfill | 🟡 synthetic generator only (real provider TBD) |
| WP1.3 Physical tracking adapter | ⬜ |
| WP2.1 Z-score vectorizer & corridor solver | ✅ |
| WP2.2 Veto / badge / player effort scorer | ✅ |
| WP3.1 k-NN twins & snapshot builder | 🟡 twin query done, snapshot builder next |
| WP3.2 – WP4.4 | ⬜ |
