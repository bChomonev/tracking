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
uv run python -m corridor.scripts.united_profile  # rank United vs the league, print summary
uv run python -m corridor.scripts.analyse         # LLM analyst writes the season read (needs backend/.env)
uv run python -m corridor.scripts.build_site      # render data/site/2026/index.html from web/united.html
```

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
