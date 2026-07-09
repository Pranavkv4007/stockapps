---
name: rerun-stock
description: Re-run the individual stock pipeline for one company with proper cache invalidation, via the Full App API, and report before/after scores. Use when asked to rerun/refresh/regenerate a stock's analysis, to verify a prompt change end-to-end, or when a company's analysis is stale or was generated without search grounding.
---

Safely re-analyzes one company through the 8-step individual pipeline. Handles the two things people always get wrong: stale caches (which silently make reruns no-ops) and losing the before-scores needed to judge the change.

**Cost note:** one run makes ~7 LLM calls including two Gemini-Pro-with-search calls, and takes several minutes. Never loop this over many companies without the user's explicit OK.

All paths relative to `D:\stocks\Apps_link\`. Use the venv python: `.venv\Scripts\python.exe`.

## Step 1 — Resolve the company and URL

Input may be a company name or a screener.in URL.

- If a URL: extract it; company name comes from Step 2's file scan (match by URL later) or from the page title after the run.
- If a name: find the URL in the sector CSVs — the `url` column of `Sector/*/*.csv`:
  ```powershell
  Get-ChildItem "Sector" -Recurse -Filter *.csv | ForEach-Object { Import-Csv $_.FullName } | Where-Object { $_.company -like "*<NAME>*" } | Select-Object company, url -First 3
  ```
- If no URL found there, ask the user for the screener.in URL (or WebSearch `site:screener.in <company>` and confirm the match with the user). Prefer the `/consolidated/` variant if it exists.

## Step 2 — Capture the BEFORE state

Run with the venv python (imports work from any cwd because backend resolves its own paths):

```powershell
.venv\Scripts\python.exe -c "
import sys, os, glob
sys.path.insert(0, os.path.join(r'D:\stocks\Apps_link', 'Full App'))
from backend.services.individual_service import extract_overall_score, extract_credibility_score, assign_signal
c = '<COMPANY>'  # exact file stem, e.g. 'CRISIL Ltd'
ind = r'D:\stocks\Apps_link\Individual_Stocks'
fin = extract_overall_score(os.path.join(ind, c + '.txt'))
con = extract_credibility_score(os.path.join(ind, c + '_concall_score.txt'))
print('financial:', fin, '| concall:', con, '| signal:', assign_signal(fin, con))
for p in glob.glob(os.path.join(r'D:\stocks\Apps_link\Sector', '*', c + '.txt')):
    print('step1 cache:', p)
concall = os.path.join(ind, c + '_concall.txt')
if os.path.exists(concall):
    txt = open(concall, encoding='utf-8', errors='replace').read()
    print('grounding:', 'SYNTHESIS (not grounded)' if 'LLM SYNTHESIS' in txt else 'search-grounded')
"
```

Record: financial score, concall score, signal, grounding status, and the list of existing files (the 3 in `Individual_Stocks/` + the Step-1 cache in `Sector/{sub_sector}/`). If the company has never been analyzed, say so — this becomes a first run, skip deletion.

## Step 3 — Confirm deletion with the user

Deleting analysis files is destructive and they cost API money to regenerate. Show the exact file list and current scores, and confirm before deleting — UNLESS the user's request already explicitly asked for a rerun/refresh of this company (then proceed). Never delete files of any other company. Delete:

- `Individual_Stocks/{Company}.txt`, `{Company}_concall.txt`, `{Company}_concall_score.txt`
- `Sector/{sub_sector}/{Company}.txt` (Step-1 cache) — keep it only if the user says the underlying screener data hasn't changed AND the prompt being tested is downstream of Step 1 (Steps 3–7 prompts). When in doubt, delete it too.

## Step 4 — Ensure the backend is running

```powershell
curl -s http://localhost:8000/api/health
```

If it fails, start it in the background (Bash tool, `run_in_background: true`):

```bash
cd "/d/stocks/Apps_link/Full App" && ../.venv/Scripts/python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

then poll `/api/health` until 200 (a few seconds).

## Step 5 — Start the pipeline

```bash
curl -s -X POST http://localhost:8000/api/pipeline/individual/start \
  -H "Content-Type: application/json" \
  -d '{"url": "<SCREENER_URL>"}'
```

Returns `{"run_id": "...", "status": "started"}`. Default models are used unless the user asked for specific ones (then pass `"models": {"step1": "...", ... "step7": "..."}` — aliases from `models.json`'s `model_options`).

## Step 6 — Monitor to completion

Poll every ~30–45 s:

```bash
curl -s http://localhost:8000/api/pipeline/status/<RUN_ID>
```

- `status: "awaiting_cache_decision"` — shouldn't happen after Step 3's deletion, but if it does (e.g. Step-1 cache was kept deliberately), resume with:
  `curl -s -X POST http://localhost:8000/api/pipeline/cache-decision/<RUN_ID> -H "Content-Type: application/json" -d '{"decision": "continue"}'` (or `"delete"` if a fully fresh run was intended).
- `status: "failed"` — read `error` and `logs`, report verbatim. Common causes: Step-1 file > 100 KB guard (diagnose the scrape, don't raise the limit), Gemini quota errors (retry later), missing API key.
- `status: "completed"` — proceed. Watch `logs` for `Falling back to LLM synthesis` on Step 6: that means the Walk-the-Talk is NOT search-grounded and the concall score is LOW-confidence.

## Step 7 — Verify and report AFTER state

Re-run the Step-2 snippet. The run is only a success if:

- [ ] All 3 output files exist in `Individual_Stocks/`
- [ ] `extract_overall_score` and `extract_credibility_score` both return numbers (if either is `None`, the LLM used a new output format — that's an extraction bug to report; fix by APPENDING a regex pass per CLAUDE.md Trap #2, never by editing the file)
- [ ] Grounding status of the new `_concall.txt` is noted

Then report to the user:

| | Before | After |
|---|---|---|
| Financial score | | |
| Concall score | | |
| Signal | | |
| Concall grounding | | |

Plus 2–3 sentences on what changed and why (from the new analysis text). If this rerun was verifying a prompt change, state explicitly whether the change had the intended effect, and remind that the before → after scores belong in the commit body.
