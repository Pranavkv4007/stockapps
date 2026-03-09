# Prompts — Stock Analysis Apps

Central reference for every LLM prompt used across the monorepo. The canonical source of truth for system prompts is `Full App/backend/services/prompts.py`; the Streamlit apps (`FullScreener/Fullscreener_app.py`, `individual/IndividualStockApp.py`) embed functionally identical copies.

## Files in This Folder

| File | Pipeline | Prompts Covered |
|------|----------|-----------------|
| `sector_pipeline.md` | Sector Screener (FullScreener / Full App) | 3 system prompts + 3 user prompt templates |
| `individual_pipeline.md` | Individual Stock (individual / Full App) | 7 system prompts + 8 user prompt templates |
| `transcript_rag.md` | Concall RAG Scorer (individual/transcript_scorer.py) | 1 system prompt + 1 user prompt template + 7 retrieval queries |

## Pipeline Overview

### Sector Pipeline (8 phases)
```
Phase 1-4  : Scraping & link extraction (no LLM)
Phase 5    : LLM extracts financial text        → system: SCREENER,  user: user_prompt_screener_sector()
Phase 6    : LLM scores companies (0-100)       → system: SCORE,     user: user_prompt_score()
Phase 7    : LLM converts score to JSON         → system: JSON,      user: user_prompt_json()
Phase 8    : CSV writing & aggregation (no LLM)
```

### Individual Pipeline (8 steps)
```
Step 0  : Scrape URL (no LLM)
Step 1  : LLM extracts financial text           → system: SCREENER_IND,   user: user_prompt_screener_ind()
Step 2  : LLM converts text → structured JSON   → system: JSON_IND,       user: create_user_json()
Step 3  : LLM selects sector KPIs/ratios        → system: KPI,            user: user_prompts_kpi()
Step 4a : Gemini Search extracts KPI values     → system: GEMINI_SEARCH,  user: user_prompts_gemini_search()
Step 4b : LLM calculates KPIs from JSON         → system: KPI_CAL,        user: user_prompts_kpi_cal()
Step 5  : LLM final analysis + 0-100 score      → system: FINAL,          user: create_user_prompt_final()
Step 6  : Gemini Search "Walk the Talk"         → (no system prompt — grounding only)  user: user_prompt_walkthetalk()
Step 7  : LLM scores management credibility     → system: CONCALL_SCORE,  user: prompt_concall_score()
```

### Transcript RAG (optional, within Step 7 path)
```
Offline transcripts (.txt/.pdf) → chunk → embed → retrieve per category → LLM scores
System: CONCALL_SCORE (same as Step 7)
User:   _build_user_prompt() with RAG context injected
```

## Editing Prompts

- **Full App pipeline**: Edit `Full App/backend/services/prompts.py` — prompts are passed to the API via request body and can also be overridden in the Full App UI.
- **FullScreener Streamlit**: Prompts are editable live in the sidebar UI; defaults match `prompts.py`.
- **Individual Streamlit**: Prompts are editable live in the sidebar UI (one text area per step).
- **Transcript RAG**: Edit `individual/transcript_scorer.py` — `SCORING_QUERIES` list and `_build_user_prompt()`.

## Critical Rules
- Do NOT simplify regex patterns in score extraction (`individual_service.py` / `IndividualStockApp.py`).
- Prompt text in `prompts.py` must stay in sync with Streamlit app defaults if the Streamlit apps are used standalone.
