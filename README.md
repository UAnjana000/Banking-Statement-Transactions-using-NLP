# FinUnderWrite

Bank-agnostic banking transaction intelligence platform (`finunderwrite` package). Ingests statements in arbitrary formats (PDF native/scanned, CSV, XLSX), normalizes them into a frozen `CanonicalTransaction` schema, and builds toward underwriting features and financial profiles.

## Pipeline

```
raw files -> Inventory -> Parser -> Schema Detection -> Normalizer -> CanonicalTransaction[]
  -> (future) Merchant Extractor -> Categorizer -> Behaviour -> Profile -> Features / Synthetic
```

## Requirements

- Python 3.12+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (scanned PDFs)
- [Poppler](https://poppler.freedesktop.org/) (PDF to image for OCR)

### Windows setup

```powershell
winget install Python.Python.3.12
winget install tesseract-ocr.tesseract
winget install oschwartz10612.Poppler
```

Restart your shell after installing so PATH updates apply. If binaries are not found, set paths in `.env`:

```env
FINUNDERWRITE_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
FINUNDERWRITE_POPPLER_PATH=C:\path\to\poppler\Library\bin
```

### Linux (Debian/Ubuntu)

```bash
sudo apt-get update && sudo apt-get install -y tesseract-ocr poppler-utils
```

## Project setup

```powershell
cd "d:\NLP project 1"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m spacy download en_core_web_sm
pre-commit install
copy .env.example .env
```

Editable install (recommended for development):

```powershell
pip install -e ".[dev]"
```

## Usage

```powershell
# Scan a folder and profile each file
finunderwrite inventory data/raw

# Or via module
python -m finunderwrite.cli inventory data/raw
```

## Data directories

| Path | Purpose |
|------|---------|
| `data/raw/` | Original statements (gitignored - never commit PII) |
| `data/interim/` | Parsed raw tables |
| `data/processed/` | Normalized transactions |

Synthetic test fixtures live in `tests/fixtures/` and are safe to commit.

## Quality checks

```powershell
ruff check src tests config
ruff format src tests config
mypy
pytest --cov=finunderwrite --cov-report=term-missing
```

## Module status

See [`PROJECT_STATE.json`](PROJECT_STATE.json) for machine-readable build state.

Implemented: contracts, inventory, parser, schema detection, normalizer, merchant (extract/categorize/enrich), behaviour, recurring, profile, features, synthetic (offline), persistence, API, CLI, tests.

## Merchant intelligence

- Extraction: rules-driven (config/merchant_rules.yaml) merchant + payment_mode parsing with rapidfuzz canonicalization.
- Categorization: hybrid tiers - rules (config/category_map.yaml) -> char-ngram TF-IDF + LogisticRegression (scikit-learn, persisted via joblib) -> optional LLM (Groq, OpenAI-compatible), OFF by default via FINUNDERWRITE_LLM_ENRICH_ENABLED.
- Enrichment: request path reads the DB cache only and queues misses; the offline finunderwrite enrich-batch command is the only bulk-network path (httpx + tenacity, robots.txt + rate limit).

```powershell
finunderwrite train-categorizer   # build + persist the Tier 2 model
finunderwrite enrich-batch        # offline: drain queue, populate enrichment cache
```

## Analytics pipeline (offline vs serving)

- Behaviour learning, recurring detection, profile building, and feature engineering are pure pandas/numpy (deterministic, no torch) and run in both the offline pipeline and the serving runtime.
- Synthetic data generation is OFFLINE-ONLY: `finunderwrite synth-generate <feature_table.csv> --n 1000 --method gaussian_copula|ctgan|tvae`. It requires `pip install -r requirements-ml.txt` (sdv + torch) and raises at import if that stack is absent, so it can never load on the web dyno. Generated datasets are saved to `data/processed/synthetic/` and registered in the DB for the API to serve.

## API + web UI

Run locally:

```powershell
uvicorn finunderwrite.api:app --reload
```

Open `http://127.0.0.1:8000/` for the dashboard (upload a statement, inspect transactions / profile / features). OpenAPI docs remain at `/docs`.

API endpoints: `GET /health`, `POST /statements` (CSV + native PDF parsed synchronously; scanned PDFs return `202` and are deferred to the offline OCR batch), `GET /transactions`, `GET /profile/{customer_id}`, `GET /features/{customer_id}`, `GET /synthetic?n=100|1000|10000` (serves pre-generated datasets only).

## Database + migrations

Driven by `FINUNDERWRITE_DATABASE_URL` (or `DATABASE_URL`): defaults to `sqlite:///local.db` for dev, Postgres for deploy (e.g. `postgresql+psycopg://user:pass@host/db`). DuckDB is a read-only local analytics layer over processed files.

```powershell
alembic upgrade head        # apply migrations
alembic revision --autogenerate -m "change"   # create a new migration
```

## Deployment (Koyeb)

1. Push this repo to GitHub (do **not** commit `.venv`, `.env`, or real bank statements).
2. Create an external Postgres database (Neon or Supabase) and copy its connection URL. Prefer the SQLAlchemy form `postgresql+psycopg://user:pass@host/db`.
3. In [Koyeb](https://app.koyeb.com/), create a **Web Service** from GitHub:
   - Builder: **Dockerfile** (`./Dockerfile`)
   - Port: `8000` (HTTP), route `/` → `8000`
   - Health check: HTTP `GET /health` on port `8000`
   - Instance: Free (or Nano/Micro if you need more RAM for large PDF ingest)
4. Set environment variables in the Koyeb service settings:

| Variable | Value |
|---|---|
| `PORT` | `8000` |
| `WEB_CONCURRENCY` | `2` |
| `PYTHONPATH` | `/app/src` |
| `FINUNDERWRITE_LOG_LEVEL` | `INFO` |
| `FINUNDERWRITE_LLM_ENRICH_ENABLED` | `false` |
| `FINUNDERWRITE_ENRICHER` | `null` |
| `FINUNDERWRITE_DATABASE_URL` | your external Postgres URL |

5. Deploy. The UI is at `/`; API docs at `/docs`.

### CLI alternative

Install the [Koyeb CLI](https://www.koyeb.com/docs/build-and-deploy/cli/installation), run `koyeb login`, then:

```bash
export FINUNDERWRITE_DATABASE_URL='postgresql+psycopg://user:pass@host/db'
sh deploy/koyeb-init.sh
```

Notes:

- `Dockerfile` builds a lightweight `python:3.12-slim` image, installs `tesseract-ocr` + `poppler-utils`, installs ONLY `requirements.txt` (no torch/sdv/sentence-transformers), and serves with gunicorn + uvicorn workers bound to `$PORT`.
- Koyeb's filesystem is ephemeral — keep operational data in external Postgres (Neon/Supabase).
- `.koyebignore` skips redeploys for docs-only commits (README, PROJECT_STATE, etc.).
- Offline vs serving split: OCR, model training, enrichment batch, and synthetic generation are offline jobs; the web service only parses CSV/native PDFs synchronously and serves pre-computed results.

## Build Log

<!-- Newest entries first -->

### 2026-07-17 — deploy: Switch hosting from Render to Koyeb (Dockerfile + CLI init script, health check /health)
### 2026-07-17 — web_ui: Polish FinUnderWrite dashboard (Newsreader/Outfit, ledger atmosphere, motion); ignore .cursor; title-only commit hygiene
### 2026-07-17 — web_ui/api/parser: Brand FinUnderWrite; 50 MB upload cap with MB-threshold errors; PDF concat hardened for duplicate camelot columns; Windows temp cleanup no longer masks ingest errors
### 2026-07-17 — web_ui: Static dashboard at `/` (upload, ledger, profile, features) served by FastAPI; gitignore hardened against venv/PII
### 2026-07-17 - api/deploy: Lightweight FastAPI service (health/statements/transactions/profile/features/synthetic), Alembic migrations, Postgres/DuckDB persistence, Dockerfile + Koyeb deploy, request-id logging, env validation, coverage gate
### 2026-07-17 - features/synthetic: Deterministic underwriting feature table and offline-only synthetic generation (GaussianCopula/CTGAN/TVAE) with import guard, fidelity + NN-distance privacy checks, requirements-ml.txt split
### 2026-07-17 - behaviour/profile: Deterministic behaviour summary, recurring detection (cadence clustering), and FinancialProfile builder with known-pattern synthetic fixtures
### 2026-07-17 - merchant: Merchant extraction, hybrid categorization (rules+sklearn, optional LLM), and defensive cache-first enrichment with SQLAlchemy persistence
### 2026-07-17 - persistence: SQLAlchemy 2.0 layer with enrichment cache/queue and LLM category cache
### 2026-07-17 - scaffold: Initial pipeline (inventory -> parser -> schema -> normalize) with synthetic fixtures and unit tests
