# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Streamlit-based stock analysis pipeline that scrapes screener.in company pages and runs a multi-step LLM pipeline to produce financial analysis, management credibility ("Walk the Talk"), and concall scoring reports.

## Commands

```bash
# Launch the app (activates venv automatically)
run.bat

# Or manually
.venv\Scripts\activate
streamlit run app.py
```

## Architecture

**Single-file app** (`app.py`, ~1235 lines) organized into 7 sections:

1. **Imports & Config** — Model constants (`GPT-4.1-mini`, `GPT-4o-mini`, `Gemini-3-pro-preview`), cached OpenAI/Gemini client init
2. **Utility Functions** — `Website` class (BS4 scraper), `llm()` dispatcher (match/case on model name), JSON cleaning, sector extraction
3. **Default Prompts** — 7 system prompts + user prompt generators for each pipeline step
4. **Session State** — `DEFAULTS` dict initializes all state keys (inputs, model choices, prompts, results, logs)
5. **Sidebar** — URL input, live API status checks (cached per session), per-step model selectors, run/reset controls
6. **Pipeline Execution** — 8 step functions (Step 0-7), two modes: full run with progress bar, or step-by-step with individual buttons
7. **Results Display** — 5 tabs: Financial Analysis, Walk the Talk, Concall Score, Intermediate Data, Logs

### Pipeline Steps & Data Flow

```
Step 0: Scrape URL → site_text, company_name, sector, sub_sector
Step 1: LLM extracts financial data from site_text (cached in Sector/{sub_sector}/)
Step 2: LLM converts financial text → structured JSON
Step 3: LLM generates sector-specific KPIs/ratios
Step 4: Gemini Search extracts KPI values (fallback: calculate from Step 2 JSON)
Step 5: LLM produces final analysis with 0-100 score → saved to Individual_Stocks/
Step 6: Gemini Search "Walk the Talk" analysis → saved to Individual_Stocks/
Step 7: LLM scores management credibility → saved to Individual_Stocks/
```

### Key Patterns

- **Multi-model dispatch**: `llm()` routes to OpenAI/GPT-4o/Gemini via match/case. Each step has its own model selector.
- **Prompt-driven**: All analysis logic lives in system prompts (editable in UI). Code changes rarely needed for analysis tweaks.
- **Caching**: Step 1 results cached as files in `Sector/{sub_sector}/{company}.txt`. API status cached in session state.
- **Gemini Search grounding**: Steps 4 and 6 use `google.genai.types.GoogleSearch` tool for real-time data. Both have fallback paths.

### Output Directories

- `Sector/` — Cached Step 1 financial text, organized by sub-sector
- `Individual_Stocks/` — Final reports: `{Company}.txt`, `{Company}_concall.txt`, `{Company}_concall_score.txt`

## Environment

- Python venv at `.venv/`
- API keys in `.env`: `OPENAI_API_KEY`, `GOOGLE_API_KEY`
- Windows-only `run.bat` launcher
