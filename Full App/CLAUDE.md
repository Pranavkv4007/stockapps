# CLAUDE.md — Full App (Stock Analysis Hub)

Unified FastAPI backend + single-page HTML frontend that combines the Sector Screener, Individual Stock Analyzer, and Visualization dashboards into one app. Also exposes pipeline execution via API with SSE streaming.

## Commands

```bash
# Launch (installs deps, starts uvicorn on port 8000, opens browser)
run.bat

# Or manually
cd "Full App"
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## Architecture

```
Full App/
├── backend/
│   ├── main.py                    # FastAPI entry point, health/search/export endpoints
│   ├── config.py                  # Paths, tier thresholds, signal colors, LLM model constants
│   ├── routers/
│   │   ├── sector.py              # /api/sector/* — combined, all, summary, detail, download
│   │   ├── individual.py          # /api/individual/* — scores, comparison, aligned, divergent
│   │   └── pipeline.py            # /api/pipeline/* — start/stream/cancel sector & individual pipelines
│   └── services/
│       ├── sector_service.py      # CSV combiner, sector aggregation (ported from ScoreVisualApp.py)
│       ├── individual_service.py  # Score extraction, signal/tier logic (ported from Individualscoreapp.py)
│       ├── llm_service.py         # OpenAI/Gemini client singletons, llm() dispatcher, JSON cleaning
│       ├── scraper_service.py     # Website class (BS4), sector/company link extraction from screener.in
│       ├── prompts.py             # ALL system/user prompts for both pipelines (exact copies from originals)
│       ├── pipeline_manager.py    # In-memory run tracking, SSE event queues, singleton PipelineManager
│       ├── sector_pipeline.py     # 8-phase sector pipeline (async, pushes SSE events)
│       └── individual_pipeline.py # 8-step individual pipeline (async, step-by-step or full run)
├── frontend/
│   └── index.html                 # Single-page app: Tailwind CSS + Alpine.js + Plotly.js
├── run.bat / run.sh               # One-command launchers
└── STOCK_APP_INSTRUCTIONS.md      # Original build spec
```

## API Endpoints

### Data APIs (read from files)
- `GET /api/health` — health check
- `GET /api/search?q=` — global search across sectors + individual stocks
- `GET /api/cross-reference/{company_name}` — combined profile if company in both datasets
- `GET /api/export-all` — ZIP download of all data
- `GET /api/sector/combined|all|summary|sectors|detail/{name}|download/*`
- `GET /api/individual/scores|comparison|aligned|divergent|missing|tier-summary|download/*|freshness`

### Pipeline APIs (execute LLM pipelines)
- `POST /api/pipeline/sector/start` — start sector pipeline (body: url, models, prompts)
- `POST /api/pipeline/individual/start` — start individual pipeline
- `POST /api/pipeline/individual/run-step` — run single step (step-by-step mode)
- `GET /api/pipeline/stream/{run_id}` — SSE event stream for real-time progress
- `GET /api/pipeline/status/{run_id}` — poll status
- `POST /api/pipeline/cancel/{run_id}` — cancel running pipeline
- `GET /api/pipeline/api-status` — test connectivity to all LLM models
- `GET /api/pipeline/prompts/sector/defaults` — default sector prompts
- `GET /api/pipeline/prompts/individual/defaults` — default individual prompts

## Frontend

Single-page HTML app using:
- **Tailwind CSS** (CDN) with dark/light mode
- **Alpine.js** for reactive state management
- **Plotly.js** for charts
- **marked.js** for markdown rendering

Modules: Dashboard, Sector Screener, Individual Stocks, Pipeline Runner

## Key Design Decisions

- **FastAPI serves frontend** via `StaticFiles` mount — single port, no separate frontend server
- **Module-level caching** in routers (lazy-loaded DataFrames, refreshable via POST /refresh)
- **Pipeline runs** tracked in-memory by singleton `PipelineManager` with async event queues for SSE
- **Prompts are centralized** in `prompts.py` — all system/user prompts for both pipelines in one file
- **LLM abstraction** in `llm_service.py` — `llm(system, user, model_name)` dispatches to OpenAI/Gemini

## Data Paths (from config.py)

- `SECTOR_DIR` → `../Sector/` (relative to Full App)
- `INDIVIDUAL_DIR` → `../Individual_Stocks/`
- `SCORES_JSON` → `../scores.json`
- Overridable via `STOCK_HUB_ROOT` env var or `.env` file in project root

## Critical: Do NOT Change

- Regex patterns in `individual_service.py` (score extraction)
- `floor(max/10)*10` filtering in `sector_service.py` (CSV combiner)
- Signal classification thresholds in `individual_service.py`
- Prompt text in `prompts.py` (exact copies from original Streamlit apps)
