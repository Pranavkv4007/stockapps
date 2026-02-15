# CLAUDE.md — FullScreener (Sector Screener Pipeline)

Streamlit app that takes a Screener.in sector URL and runs a multi-phase LLM pipeline to analyze all companies in that sector.

## Commands

```bash
# Launch (activates venv, runs streamlit)
run.bat

# Or manually
cd Apps_link
.venv\Scripts\activate
streamlit run FullScreener\Fullscreener_app.py
```

## Architecture

**Single-file app** (`Fullscreener_app.py`, ~970 lines) organized into 8 sections:

1. **Imports & Config** — Model constants, path setup, `SECTOR_DIR`
2. **Cached Clients** — `@st.cache_resource` OpenAI/Gemini client init
3. **Website Class & Utilities** — BS4 scraper, `llm()` dispatcher, sector link extraction
4. **Default Prompts** — 3 system prompts: Screener extraction, Score calculation, JSON conversion
5. **Session State** — `DEFAULTS` dict with all state keys
6. **Sidebar** — URL input, API status, model selectors, run/reset buttons
7. **Pipeline Execution** — 8-phase sequential pipeline with `st.status()` progress
8. **Results Display** — 4 tabs: Execution Status, Final Scores, Company Details, Logs

### Pipeline Phases

```
Phase 1: Scrape sector URL → title, page count
Phase 2: Get company links from all pages
Phase 3: Get company names from links
Phase 4: Get sector/sub-sector classification
Phase 5: LLM extracts financial data for each company → saved as .txt
Phase 6: LLM calculates score for each company → saved as _Score.txt
Phase 7: LLM creates JSON summaries → saved as progress.json
Phase 8: Save final JSON + CSV files
```

### Output

All output goes to `Sector/{sector_title}/`:
- `{Company}.txt` — extracted financial data
- `{Company}_Score.txt` — LLM-generated score analysis
- `{sector_title}.json` — array of `{company, score, key_metrics, explanation}`
- `{sector_title}.csv` — `company, score, Sector, url` columns
- `progress.json` — resumable progress tracker for Phase 7

### Key Patterns

- **Multi-model dispatch**: `llm()` routes to OpenAI (`gpt-4.1-mini`), GPT-4o (`gpt-4o-mini`), or Gemini (`gemini-3-pro-preview`)
- **File caching**: Phase 5 skips companies with existing .txt files; Phase 6 skips existing _Score.txt files
- **Resumability**: Phase 7 JSON creation resumes from `progress.json`
- **Rate limiting**: `time.sleep(1)` between scraping/LLM calls
- **Max 100 LLM calls** per Phase 5 run (safety limit)

### Input

- Screener.in sector URL, e.g., `https://www.screener.in/market/IN06/IN0601/IN060103/IN060103001/`
- Model choices for extraction and scoring (selectable per step)
- Editable system prompts (3 prompts, editable in UI)

## Files

- `Fullscreener_app.py` — the app
- `Screener.ipynb` — original Jupyter notebook this was ported from
- `Instructions.txt` — original build instructions
- `run.bat` — launcher
