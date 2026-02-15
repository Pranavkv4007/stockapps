# CLAUDE.md — individual (Individual Stock Analysis Pipeline)

Streamlit app that takes a single Screener.in company URL and runs an 8-step LLM pipeline to produce financial analysis, management credibility ("Walk the Talk"), and concall scoring reports.

## Commands

```bash
# Launch the app (activates venv automatically)
run.bat

# Or manually
cd Apps_link
.venv\Scripts\activate
streamlit run individual\IndividualStockApp.py
```

## Architecture

**Single-file app** (`IndividualStockApp.py`, ~1240 lines) organized into 7 sections:

1. **Imports & Config** — Model constants (`GPT-4.1-mini`, `GPT-4o-mini`, `Gemini-3-pro-preview`), cached OpenAI/Gemini client init
2. **Utility Functions** — `Website` class (BS4 scraper), `llm()` dispatcher (match/case on model name), JSON cleaning, sector extraction helpers
3. **Default Prompts** — 7 system prompts + user prompt generators for each pipeline step
4. **Session State** — `DEFAULTS` dict initializes all state keys (inputs, model choices per step, prompts, results, logs)
5. **Sidebar** — URL input, live API status checks, per-step model selectors (7 selectors), step-by-step toggle, run/reset controls
6. **Pipeline Execution** — 8 step functions (Step 0-7), two modes: full run with progress bar, or step-by-step with individual buttons and dependency checking
7. **Results Display** — 5 tabs: Financial Analysis, Walk the Talk, Concall Score, Intermediate Data, Logs

### Pipeline Steps & Data Flow

```
Step 0: Scrape URL → site_text, company_name, sector, sub_sector
Step 1: LLM extracts financial data from site_text (cached in Sector/{sub_sector}/)
Step 2: LLM converts financial text → structured JSON
Step 3: LLM generates sector-specific KPIs/ratios (JSON output)
Step 4: Gemini Search extracts KPI values (fallback: calculate from Step 2 JSON), then cleans output
Step 5: LLM produces final analysis with 0-100 score → saved to Individual_Stocks/{Company}.txt
Step 6: Gemini Search "Walk the Talk" analysis → saved to Individual_Stocks/{Company}_concall.txt
Step 7: LLM scores management credibility → saved to Individual_Stocks/{Company}_concall_score.txt
```

### Key Patterns

- **Multi-model dispatch**: `llm()` routes to OpenAI/GPT-4o/Gemini via match/case. Each step has its own model selector.
- **Prompt-driven**: All analysis logic lives in system prompts (editable in UI). Code changes rarely needed for analysis tweaks.
- **Caching**: Step 1 results cached as files in `Sector/{sub_sector}/{company}.txt`. API status cached in session state.
- **Gemini Search grounding**: Steps 4 and 6 use `google.genai.types.GoogleSearch` tool for real-time data. Both have fallback paths.
- **Step-by-step mode**: Each step can be run individually with dependency checking (e.g., Step 1 requires Step 0 output).
- **Text cleaning**: `clean_text_for_llm()` removes citations, emojis, broken table rows before passing to LLM.

### Input

- Screener.in company URL, e.g., `https://www.screener.in/company/MAHABANK/consolidated/`
- Model choices per step (7 selectable models)
- 7 editable system prompts

### Output Directories

- `Sector/{sub_sector}/` — Cached Step 1 financial text
- `Individual_Stocks/` — Final reports: `{Company}.txt`, `{Company}_concall.txt`, `{Company}_concall_score.txt`

## Files

- `IndividualStockApp.py` — the app (~1240 lines)
- `run.bat` — launcher (activates venv, runs streamlit)

## Environment

- Python venv at `../.venv/`
- API keys in `../.env`: `OPENAI_API_KEY`, `GOOGLE_API_KEY`
- Windows-only `run.bat` launcher
