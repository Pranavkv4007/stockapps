# CLAUDE.md — MyHoldings (Portfolio Analysis App)

Streamlit app for tracking personal stock holdings. Manages a portfolio stored in `holdings.json`, runs individual analysis pipelines on each holding, and displays a unified portfolio dashboard with insights.

## Commands

```bash
# Launch
run.bat

# Or manually
cd MyHoldings
streamlit run MyHoldingsApp.py
```

## Architecture

Single-file Streamlit app (`MyHoldingsApp.py`) with 4 tabs:
1. **Portfolio Dashboard** — Metrics, charts, holdings table
2. **Manage Holdings** — Add/remove holdings, bulk import, export
3. **Run Analysis** — Execute individual pipelines per holding with progress tracking
4. **Portfolio Insights** — Score comparisons, aligned/divergent, tier distribution, recommendations

## Code Reuse

Imports from `Full App/backend/services/` via `sys.path`:
- `backend.config` — paths, model constants, tier thresholds
- `backend.services.llm_service` — `llm()`, `gemini_llm_kpi()`, `clean_and_parse_json()`, `clean_text_for_llm()`
- `backend.services.scraper_service` — `Website`, `get_subsector_details()`, `get_sector_names()`
- `backend.services.prompts` — all prompt constants
- `backend.services.individual_service` — `extract_overall_score()`, `extract_credibility_score()`, `assign_tier()`, `assign_signal()`

## Data

- `holdings.json` — persistent holdings store (auto-created)
- Reads/writes to `../Individual_Stocks/` and `../Sector/` (shared data dirs)

## Critical: Do NOT Change

- Regex patterns in score extraction (imported from individual_service.py)
- Pipeline step logic must match IndividualStockApp.py exactly
- Signal/tier classification must stay consistent with other apps
