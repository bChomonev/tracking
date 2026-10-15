# Corridor Engine — agent guide

Post-match batch engine that audits football performances against empirical 90% Win / 85% Loss
corridors and publishes immutable static JSON. Read `docs/TDP-001-v1.1.md` (product + math) and
`docs/ARCHITECTURE.md` (stack) for direction — they are a compass, not a contract.
**`docs/DECISIONS.md` records every decision that deviates from or fills gaps in them; add an
entry whenever you make a design call.**

## Commands (run from `backend/`)
- `docker compose up -d` (repo root) — Postgres 16 + pgvector on localhost:5433
- `uv sync` · `uv run pytest` · `uv run ruff check . && uv run ruff format --check .`
- `uv run alembic upgrade head` · `uv run alembic check` (must report no drift)
- `uv run python -m corridor.scripts.seed_synthetic` — seed synthetic history + calibrate

- Site (Premier League + La Liga, D-029; every script takes `--league pl|laliga`; analyst for United only, D-022): `build_season` (+ `--competition ucl`) → `united_profile` → `predictions` → `previews` → `analyse` → `build_site` (see README); `update` automates it after each match (D-018). Never commit `data/` or `backend/.env`.

## Rules
1. Vectors are `halfvec(12)` in SQL and `np.float16` in Python. Dimension order, weights and
   directions are defined only in `corridor/engine/metrics.py`; changing them requires recalibration.
2. `corridor/engine/` is pure NumPy — no DB or I/O imports.
3. No math on the read path: API/read endpoints serve pre-computed snapshots/columns only.
4. Twin searches must exclude the audited match and anything at/after its kickoff.
5. Tests: seed RNGs (`np.random.default_rng(42)`); DB tests are marked `db` and skip if Postgres
   is down. Run `uv run pytest` before finishing any task.
6. Schema changes go through a new Alembic revision; keep `db/models.py` in sync.
