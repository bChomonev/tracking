# Corridor Engine

Football Performance Corridor & Effort Intelligence Platform. After every match, a batch job
scores each team's 12-dimension performance profile between an empirical **90% Win Ceiling** and
**85% Loss Floor**, finds its 50 closest historical twins with pgvector, audits player effort,
and publishes an immutable static JSON audit to the edge.

- Product & math: [`docs/TDP-001-v1.1.md`](docs/TDP-001-v1.1.md)
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Decisions log: [`docs/DECISIONS.md`](docs/DECISIONS.md)

## Quickstart

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
