# System Architecture & Technology Stack Specification (SYS-ARCH-001)

**System Name:** Football Performance Corridor & Effort Engine

**Document Version:** 1.0

**Status:** Approved for Implementation

**Companion Documents:** `docs/TDP-001-v1.1.md`

---

## 1. Architectural Principles & System Boundary

The platform is designed around a single core constraint: **high-concurrency matchday traffic must be completely decoupled from data processing.**

```
[ Data Providers ] (Opta / UEFA / Open Datasets)
       │
       ▼ (Batch trigger at FT + 10 mins)
┌────────────────────────────────────────────────────────┐
│  WRITE PATH (Asynchronous Python Worker)               │
│  • Raw stats normalization -> possession-neutral rates │
│  • 12-dim Z-score vectorization -> halfvec(12)         │
│  • Single pgvector HNSW k-NN lookup (<->)              │
│  • 90% Win / 85% Loss Corridor math & Veto flags       │
│  • Grounded LLM Tactical Autopsy synthesis             │
│  • Compile canonical MatchAuditProjection JSON         │
└────────────────────────────────────────────────────────┘
       │
       ├───► Persists to PostgreSQL 16 (Historical Archive)
       │
       ▼ (Atomic upload)
┌────────────────────────────────────────────────────────┐
│  READ PATH (Immutable Edge Tier)                       │
│  • Cloudflare R2 / S3 / Edge KV Store                  │
│  • Static asset: /audits/{season}/{match_id}.json      │
│  • Cache-Control: public, max-age=31536000, immutable  │
└────────────────────────────────────────────────────────┘
       ▲
       │ (100% of fan & creator traffic: <15ms p95)
[ Web / Mobile Clients & Social Receipt Cards ]

```

### Core Invariants

1. **Compute-Once on Write, Serve-Millions from Edge:** End-user read queries never execute live SQL joins, Z-score normalizations, or vector distance scans. Every match audit is computed once 10 minutes after full-time and published as an immutable static JSON projection.
2. **Unified Relational + Vector Storage:** PostgreSQL 16 with `pgvector` (`halfvec(12)`) serves as the sole database. No external vector databases (Pinecone, Qdrant, Milvus) are permitted.
3. **Deterministic Math Over Linguistic Tokens:** Similarity search is purely mathematical. Stats are never converted to text strings for LLM embeddings.
4. **Zero-Hallucination AI Layer:** The LLM is strictly a narrative formatter. It receives a pre-computed JSON payload with zero arithmetic responsibilities.

---

## 2. Technology Stack Matrix

| Layer | Technology | Version | Architectural Justification |
| --- | --- | --- | --- |
| **Language & Runtime** | **Python** | `3.12+` | Native support for vectorized math (`numpy`, `scipy`), async database drivers, and sports scraping ecosystems. |
| **Package & Env Manager** | **uv** (by Astral) | `Latest` | 10–100x faster dependency resolution and virtualenv management than Poetry/Pip; single lockfile (`uv.lock`). |
| **Relational & Vector DB** | **PostgreSQL + `pgvector**` | `16.x` / `v0.7+` | Unified ACID storage for relational match fixtures, player telemetry, and HNSW-indexed 16-bit feature vectors (`halfvec`). |
| **ORM & Migrations** | **SQLModel + Alembic** | `SQLModel 0.0.16+` | Combines SQLAlchemy 2.0 performance with Pydantic v2 data validation and schema re-use across the API layer. |
| **Vector Math Engine** | **NumPy & SciPy** | `1.26+` | Zero-copy array operations for rolling Z-score normalization ($\mu, \sigma$), Euclidean distance, and quantile regression. |
| **Backend API Framework** | **FastAPI** | `0.110+` | High-throughput asynchronous REST API, auto-generated OpenAPI 3.1 schemas, and direct TypeScript type generation. |
| **Job Scheduling** | **APScheduler / Cron** | `3.10+` | Lightweight, fixture-aware scheduler. Triggers post-match processing jobs at `Kickoff + 115m` and reconciliation at `Kickoff + 240m`. |
| **Object Storage / CDN** | **Cloudflare R2 + Workers** | `Edge` | S3-compatible zero-egress-fee static JSON and image hosting. Global edge caching (`s-maxage=31536000, immutable`). |
| **Frontend Framework** | **Next.js (App Router)** | `14.2+ / 15` | Server-Side Rendering (SSR) for static match pages, dynamic OpenGraph card generation via `@vercel/og` / Satori. |
| **Styling & Components** | **Tailwind CSS + Lucide** | `v3.4+` | Utility-first responsive design optimized for second-screen mobile browsing and high-contrast match receipts. |
| **LLM Inference** | **Claude 3.5 Sonnet / GPT-4o** | API | Ingests pre-computed JSON to produce the 3-paragraph Post-Match Tactical Autopsy. Cost: ~$0.015 per match. |
| **Local Dev Container** | **Docker Compose** | `Compose v2` | One-command bootstrap of PostgreSQL 16 with `pgvector` extension pre-installed. |

---

## 3. Storage Architecture & Vector Schema

### 3.1 Database Topology

```
           ┌──────────────┐
           │    teams     │
           └──────┬───────┘
                  │ 1:N
                  ▼
           ┌──────────────┐
           │   matches    │
           └──────┬───────┘
                  │
        ┌─────────┴─────────┐
    1:N │               1:N │
        ▼                   ▼
┌──────────────────┐  ┌────────────────────┐
│team_match_       │  │player_match_       │
│performances      │  │performances        │
│(stats_vector     │  │(effort_score,      │
│ halfvec(12))     │  │ passenger_status)  │
└──────────────────┘  └────────────────────┘
        │
    1:1 │ (Snapshot trigger)
        ▼
┌────────────────────────┐
│ match_audit_snapshots  │
│ (canonical JSONB)      │
└────────────────────────┘

```

### 3.2 Feature Vector Geometry (`halfvec(12)`)

Every team performance is vectorized into a 12-dimensional, 16-bit float array. Each dimension corresponds to a normalized rate metric across the 4 Tactical Stacks:

$$\mathbf{v} = [z_1, z_2, z_3, \dots, z_{12}] \in \mathbb{R}^{12}$$

Where $z_i = d_i \cdot w_i \cdot \left(\frac{x_i - \mu_i}{\sigma_i}\right)$:

* $\mu_i, \sigma_i$: Rolling 365-day mean and standard deviation across Europe's Top-5 leagues.
* $d_i \in \{+1, -1\}$: Direction inverter ($-1$ for metrics where lower is better, ensuring positive coordinates always represent superior performance).
* $w_i$: Feature weight scaling factor.

```
Dim  Metric Key               Stack                  Direction  Weight (w)  Description
───  ───────────────────────  ─────────────────────  ─────────  ──────────  ───────────────────────────────
0    dist_per_90_km           Work Rate & Press      +1         1.0         Total team distance covered
1    sprints_per_min_oop      Work Rate & Press      +1         1.3         Sprints per min out-of-possession
2    ppda                     Work Rate & Press      -1         1.5         Passes per defensive action
3    field_tilt_pct           Progression/Territory  +1         1.4         Final-third pass volume share
4    line_breaks_per_100_tch  Progression/Territory  +1         1.5         Line-breaking vertical passes
5    box_touches_per_90       Progression/Territory  +1         1.2         Touches inside opposition box
6    npxg_created             Attacking Execution    +1         1.8         Non-penalty Expected Goals
7    npxg_per_shot            Attacking Execution    +1         1.6         Average shot quality / selection
8    finishing_delta          Attacking Execution    +1         1.1         xGOT minus npxG (ball striking)
9    npxg_conceded            Defensive Transition   -1         1.8         Non-penalty xG allowed
10   npxga_per_shot_faced     Defensive Transition   -1         1.4         Quality of chances conceded
11   gk_goals_prevented       Defensive Transition   +1         1.0         PSxG faced minus goals conceded

```

### 3.3 DDL Specification (`migrations/001_initial_schema.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Teams Table
CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(120) NOT NULL,
    short_code VARCHAR(10) NOT NULL,
    competition_tier SMALLINT NOT NULL DEFAULT 1,
    is_benchmark_cohort BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Matches Table
CREATE TABLE matches (
    id BIGSERIAL PRIMARY KEY,
    external_id VARCHAR(64) UNIQUE NOT NULL,
    competition_id VARCHAR(32) NOT NULL,
    season VARCHAR(12) NOT NULL,
    kickoff_utc TIMESTAMPTZ NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'SCHEDULED',
    home_team_id INT REFERENCES teams(id),
    away_team_id INT REFERENCES teams(id),
    home_goals SMALLINT DEFAULT 0,
    away_goals SMALLINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Team Performance & Feature Vectors
CREATE TABLE team_match_performances (
    id BIGSERIAL PRIMARY KEY,
    match_id BIGINT REFERENCES matches(id) ON DELETE CASCADE,
    team_id INT REFERENCES teams(id),
    opponent_id INT REFERENCES teams(id),
    is_home BOOLEAN NOT NULL,
    result CHAR(1) NOT NULL,
    points SMALLINT NOT NULL,

    -- Raw Core Metrics
    possession_pct NUMERIC(4,1) NOT NULL,
    distance_km NUMERIC(5,1),
    sprints_count SMALLINT,
    npxg_created NUMERIC(4,2) NOT NULL,
    npxg_conceded NUMERIC(4,2) NOT NULL,
    ppda NUMERIC(4,1) NOT NULL,
    field_tilt_pct NUMERIC(4,1) NOT NULL,

    -- Pre-Computed Corridor Scores (0-100)
    overall_corridor_score NUMERIC(4,1),
    work_rate_stack_score NUMERIC(4,1),
    progression_stack_score NUMERIC(4,1),
    attacking_stack_score NUMERIC(4,1),
    defensive_stack_score NUMERIC(4,1),
    verdict_badge VARCHAR(32) NOT NULL,

    -- 12-Dimensional 16-bit Quantized Vector
    stats_vector halfvec(12) NOT NULL,
    raw_metrics JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(match_id, team_id)
);

-- HNSW Index for Euclidean Distance Similarity
CREATE INDEX idx_team_perf_halfvec_hnsw 
ON team_match_performances USING hnsw (stats_vector halfvec_l2_ops)
WITH (m = 16, ef_construction = 64);

-- Benchmark Vectors (90% Win Ceiling and 85% Loss Floor)
CREATE TABLE benchmark_corridors (
    id SERIAL PRIMARY KEY,
    season VARCHAR(12) NOT NULL,
    cohort_name VARCHAR(64) NOT NULL,
    win_90_centroid halfvec(12) NOT NULL,
    loss_85_centroid halfvec(12) NOT NULL,
    metric_scales JSONB NOT NULL, -- stores means and stds for normalization
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- CQRS Snapshot Storage
CREATE TABLE match_audit_snapshots (
    match_id BIGINT NOT NULL,
    team_id INT NOT NULL,
    payload JSONB NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY(match_id, team_id)
);

```

---

## 4. Execution Pipeline & Data Flow

```
[Kickoff + 115 min] ──► Scheduled Cron Trigger
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 1. INGESTION WORKER (scripts/batch_match_processor.py)                │
│    • Ingest match events + optical physical totals                     │
│    • Validate data completeness (100% outfield players accounted for)  │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. MATHEMATICAL NORMALIZATION & VECTORIZATION                          │
│    • Fetch active (mean, std) from benchmark_corridors                 │
│    • Compute 12 possession-adjusted rates                              │
│    • Calculate Z-scores and construct stats_vector halfvec(12)         │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. PGVECTOR SIMILARITY SEARCH (Single SQL Query)                       │
│    • SELECT ... FROM team_match_performances                           │
│      ORDER BY stats_vector <-> target_vector LIMIT 50;                 │
│    • Aggregate empirical Win %, Draw %, Loss %, and Expected Points    │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. CORRIDOR POSITION & VETO EVALUATION                                 │
│    • Compute Euclidean distances D_best and D_worst                    │
│    • Calculate Corridor Score: (D_worst / (D_best + D_worst)) * 100    │
│    • Check Stack Vetoes (Individual stack score < 18.0)                │
│    • Flag MIRAGE_WIN, UNLUCKY_LOSS, or ELITE_DOMINANCE                 │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 5. GROUNDED AI AUTOPSY SYNTHESIS                                       │
│    • Serialize step 1-4 results into strict, math-free JSON prompt     │
│    • Generate 3-paragraph executive tactical summary                   │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 6. MATERIALIZATION & STATIC EDGE PUBLISHING                            │
│    • Upsert canonical payload to match_audit_snapshots table           │
│    • Write static JSON to Cloudflare R2: /audits/2026/{match_id}.json  │
│    • Generate OpenGraph Match Receipt image (1200x675 PNG)             │
└────────────────────────────────────────────────────────────────────────┘

```

---

## 5. Directory Scaffolding & Repository Layout

```
corridor-engine/
├── .github/
│   └── workflows/
│       ├── test.yml             # uv run pytest, ruff format & lint
│       └── deploy.yml           # Database migration & static worker deploy
├── docs/
│   ├── TDP-001-v1.1.md          # Product design proposal & requirements
│   ├── ARCHITECTURE.md          # This technical specification
│   └── adr/                     # Architecture Decision Records (ADR-01 to ADR-08)
├── docker-compose.yml           # PostgreSQL 16 + pgvector container
├── pyproject.toml               # Python 3.12 dependencies managed by uv
├── uv.lock                      # Deterministic lockfile
├── alembic.ini                  # Migration environment configuration
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/   # /matches, /teams, /benchmarks
│   │   │       └── router.py
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic Settings (DB URLs, API keys)
│   │   │   └── database.py      # Async engine & session pooling
│   │   └── schemas/             # Pydantic v2 contract schemas
│   ├── engine/
│   │   ├── normalizer.py        # Possession-rate adjustments
│   │   ├── vectorizer.py        # Z-score halfvec(12) calculation
│   │   ├── corridor_solver.py   # D_best, D_worst, Veto logic
│   │   └── player_effort.py     # Passenger Floor & Effort Index
│   ├── migrations/
│   │   └── versions/            # Versioned SQL migrations
│   └── scripts/
│       ├── seed_historical.py   # Top-5 European leagues 5-year backfill
│       ├── calibrate_lines.py   # Solves rolling 90% Win & 85% Loss lines
│       └── post_match_batch.py  # End-to-end post-whistle audit pipeline
├── frontend/                    # Next.js 14+ App Router
│   ├── src/
│   │   ├── app/
│   │   │   ├── matches/[id]/    # Match Corridor Dashboard
│   │   │   └── api/og/route.tsx # Dynamic 1200x675 Social Receipt generator
│   │   ├── components/
│   │   │   ├── corridor/        # 4-Stack dual-line visualizers
│   │   │   ├── twins/           # 50 Historical Twins proof drawer
│   │   │   └── players/         # Sortable Player Effort & Passenger table
│   │   └── lib/
│   │       └── api-client.ts    # Reads static /audits/{id}.json
│   └── package.json
└── AGENT.md                     # Instructions and rules for coding agents

```

---

## 6. Service-Level Objectives & Production Limits

| Metric | Target SLO | Implementation Strategy |
| --- | --- | --- |
| **Post-Match Batch Latency** | $< 3.5\text{ seconds}$ | Ingestion, vectorization, and SQL $k$-NN run as a single compiled pipeline in Python/PostgreSQL. |
| **CDN Read Latency** | $< 15\text{ ms (p95)}$ | Edge hosting via Cloudflare R2 / Pages; zero database hits on page loads. |
| **HNSW Index Scan Latency** | $< 2.5\text{ ms}$ | `halfvec(12)` reduces index RAM footprint by 50%; entire graph resides in Postgres `shared_buffers`. |
| **AI Synthesis Cost** | $< \$0.02\text{ / match}$ | Structured, bounded prompt (~1,200 tokens); triggered exactly once per match. |
| **Total MVP Run Cost** | $< \$30\text{ / month}$ | Single VPS / managed DB instance + Cloudflare free/standard tier. |

---

## 7. Instructions for Coding Agents (`AGENT.md` Rules)

When using autonomous coding agents (Claude Code CLI, OpenCode, Cursor, Aider) in this repository, the agent must adhere to the following rules:

1. **Verify Database Extensions First:** Never run vector queries without verifying `CREATE EXTENSION IF NOT EXISTS vector;`.
2. **Strict Vector Format:** Always use `halfvec(12)` in table definitions and NumPy `float16` when constructing embedding arrays.
3. **No Dynamic Math in Read Endpoints:** Endpoints under `backend/app/api/` must read pre-computed fields from `match_audit_snapshots` or `team_match_performances`. Do not perform on-the-fly Euclidean distance loops or Z-score normalization inside request handlers.
4. **Test Before Commit:** Always execute `uv run pytest tests/` before completing any work package task.
5. **Deterministic Seed Data:** When generating synthetic fixtures for unit tests, seed NumPy's RNG (`np.random.seed(42)`) to ensure reproducible vectors and corridor outputs.

---