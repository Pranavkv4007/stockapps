---
name: data-doctor
description: Health audit of all generated data — Individual_Stocks/, Sector/, scores.json, Sector_Combined.csv. Finds score-extraction failures, missing companion files, un-grounded concall analyses, filename convention violations, stale combined rows, and incomplete pipeline runs. Use when a dashboard number looks wrong, a company is missing from a view, after bulk pipeline runs, or when asked to check/validate/audit the data.
---

Read-only diagnosis of the output data that all dashboards depend on. Run it before touching any extraction code or prompt — most "the app is broken" reports are actually one bad data file.

## Run

```powershell
.venv\Scripts\python.exe .claude\skills\data-doctor\doctor.py
```

No network, no LLM calls, writes nothing. Exit code = number of ERROR findings.

## Interpret and report

Summarize to the user by severity. For each finding class, the correct response is:

| Finding | Meaning | Correct fix |
|---|---|---|
| `overall/credibility score NOT extractable` | LLM emitted a format none of the regex passes match | Read the file, find the score line, APPEND a new regex pass at the END of the extractor in BOTH `individual_service.py` and `Visualizations/Individualscoreapp.py`, then dry-run all files (no previously-extracted value may change). Never edit the data file, never modify existing passes (CLAUDE.md Trap #2) |
| `filename violates underscore convention` | A stray `{Company}_something.txt` in `Individual_Stocks/` | Ask the user what it is; if scratch, move it out of the data dir. Never silently delete |
| `Walk-the-Talk is NOT search-grounded` | Step 6 fell back to training-data synthesis; concall score is LOW confidence | Offer `/rerun-stock <company>` when Gemini quota/search is available. Do NOT hand-edit the score |
| `missing _concall.txt / _concall_score.txt` | Pipeline stopped mid-run | Offer `/rerun-stock` (its caching resumes cheaply if the base .txt exists and Step-1 cache is kept) |
| `scores.json` mismatch/missing entries | Cache file is older than the data files | Regenerate: `load_individual_scores()` rebuilds it — easiest via `curl -s localhost:8000/api/individual/scores` with the backend running, or by opening the Individualscoreapp dashboard. Never hand-edit |
| `Sector_Combined.csv stale rows / floor violated` | Combined file predates sector folder changes (folders deleted/renamed) | Regenerate via `run_csv_combiner()` — `curl -s localhost:8000/api/sector/combined` or the ScoreVisualApp refresh button. Never hand-edit |
| `progress.json present` / `Phase 6 incomplete` | Sector run was interrupted | Informational; rerunning the sector pipeline resumes from cache. Starting that run needs the user's OK (cost) |
| `> 100 KB` file | Exceeds the pipeline's token-safety guard; downstream steps will refuse it | Inspect for scrape junk (nav text, peer tables). Fix the scrape/extraction, delete the file, rerun. Don't raise the guard |
| `analysis is N days old` | Stale | Mention only; rerunning is the user's call (cost) |

## Rules

- This skill diagnoses; it does not bulk-fix. Every regeneration or deletion beyond the two cache files (`scores.json`, `Sector_Combined.csv`) needs the user's explicit go-ahead.
- If pandas import fails, you're on system python — rerun with `.venv\Scripts\python.exe`.
- When several companies fail extraction with the SAME new format, that's one fix (one appended regex pass), not N reruns — say so.
- After any fix, rerun the doctor and show the before/after ERROR count.
