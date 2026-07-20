# US Stocks Port — Master Plan

Blueprint for building a **US-market twin** of the Apps_link Indian stock analysis monorepo.
This document is self-contained: a model (or engineer) starting from an empty repository can
build the full system from it — architecture, workflows, prompts strategy, scoring math,
data documentation, build milestones, testing, and error-resolution playbooks.

Source system: `D:\stocks\Apps_link` (India, screener.in). Target: new repo, US listed equities.

---

## 1. Objective and Scope

Reproduce the two core workflows for US stocks with identical scoring semantics:

1. **Sector pipeline** — given a sector/industry, enumerate its companies, extract each
   company's financials, produce a 0–100 financial score per company, and emit
   `{sector}.csv` + `{sector}.json` plus a combined cross-sector CSV.
2. **Individual pipeline** — given one company, produce (a) a financial analysis with a
   0–100 score, (b) a "Walk the Talk" management-guidance-vs-outcome analysis from
   earnings calls, and (c) a 0–100 management credibility (concall) score.

Plus the supporting layers: score extraction from LLM text output, `scores.json`,
tier/signal classification, dashboards, and a FastAPI hub exposing everything.

**Unchanged by design** (these are frozen constants; all historical comparability depends on them):

| Constant | Value |
|---|---|
| Financial score dimensions/weights | KPI Benchmark 40 / Financial Performance 20 / Growth 15 / Health & Stability 15 / Valuation 10 (sum = 100) |
| Sector-pipeline score weights | Financial Health 25% / Profitability 25% / Growth Quality 20% / Valuation 15% / Competitive Position 15% |
| Concall category weights | Revenue 30% / EBITDA-Margin 25% / Product Launch 20% / Strategic 15% / Regulatory 10% |
| Achievement bands | >105% = 100 pts, 95–105% = 85, 85–94% = 60, <85% = 30; "inferred" guidance capped at 65 |
| Tier thresholds | ≥80 Excellent, ≥60 Good, ≥40 Average, else Weak |
| Signal rules | fin≥75 & con≥75 Strong Buy; fin≥75 & con<60 "Financials Strong, Concall Weak" (and mirror); both ≥60 Moderate Buy; both <50 Avoid; else Mixed |
| Combined CSV filter | keep rows with `score >= floor(sector_max/10)*10` |
| Safety guards | 1 s sleep between scrape requests; max 100 LLM calls per sector Phase-5 run; 100 KB max per extraction file (20 KB skip threshold before scoring) |

---

## 2. Architecture (carried over 1:1)

```
us-stocks/
├── Full App/                     # PRIMARY: FastAPI backend + single-page frontend
│   ├── backend/
│   │   ├── main.py               # health, search, export endpoints; serves frontend
│   │   ├── config.py             # paths, TIER_THRESHOLDS, hard-fails on missing model keys
│   │   ├── routers/              # sector.py, individual.py, pipeline.py (SSE streaming)
│   │   └── services/
│   │       ├── prompts.py        # CANONICAL home of ALL prompts
│   │       ├── llm_service.py    # llm(system,user,alias) dispatcher; OpenAI/Gemini/Claude clients
│   │       ├── scraper_service.py# data-source client (see §3)
│   │       ├── edgar_service.py  # NEW: SEC EDGAR client (ticker→CIK, companyfacts, filings)
│   │       ├── sector_pipeline.py    # 8 phases, async, SSE events
│   │       ├── individual_pipeline.py# 8 steps, async, step-by-step or full
│   │       ├── sector_service.py     # CSV combiner (floor filter), aggregation
│   │       ├── individual_service.py # score-extraction regexes, tier/signal logic
│   │       └── pipeline_manager.py   # in-memory run tracking + SSE queues
│   └── frontend/index.html       # Tailwind + Alpine.js + Plotly single page
├── FullScreener/Fullscreener_app.py   # Streamlit twin of sector pipeline
├── individual/IndividualStockApp.py   # Streamlit twin of individual pipeline
├── individual/transcript_scorer.py    # RAG scorer over user-supplied transcript PDFs
├── Visualizations/                    # 2 read-only Streamlit dashboards
├── Sector/                            # output: {Industry}/{Company}.txt, _Score.txt, {sector}.csv/.json
├── Individual_Stocks/                 # output: {Company}.txt, _concall.txt, _concall_score.txt
├── scores.json                        # {"overall_scores": {...}, "credibility_scores": {...}}
├── Sector_Combined.csv                # company,score,Sector,url
├── models.json                        # ONLY place model IDs live; aliases → IDs
├── prompts/                           # markdown docs of every prompt (third copy)
├── tests/                             # NEW in this port — see §8
├── .env                               # OPENAI_API_KEY, GOOGLE_API_KEY, ANTHROPIC_API_KEY, SEC_CONTACT_EMAIL
└── CLAUDE.md                          # operating manual (port the Law-#1 copy map + traps)
```

**Law #1 (inherited, non-negotiable):** prompts, thresholds, regexes, and pipeline logic exist in
multiple copies (prompts.py → Streamlit apps → prompts/*.md docs). Every change lands in every
copy in the same commit. Build a `/prompt-sync`-style audit script on day one (§8.5).

**Recommended simplification for the new repo:** make the Streamlit apps import the pipeline
functions and prompts from `Full App/backend/services/` instead of duplicating them. This
eliminates the largest maintenance hazard of the original. If true single-sourcing isn't
possible (Streamlit needs sync wrappers), keep the copy-map + audit-script discipline.

---

## 3. Data Sources — the one big change

screener.in (India-only) is replaced by a two-tier US stack:

### 3.1 Primary page source: stockanalysis.com (scrape-shaped parity)

Closest US analog to screener.in: clean HTML tables, per-company pages, sector/industry lists.

| screener.in concept | stockanalysis.com equivalent |
|---|---|
| `/company/{name}/` page | `/stocks/{ticker}/` (overview + key stats) |
| P&L / BS / CF tables on one page | `/stocks/{ticker}/financials/` , `.../balance-sheet/` , `.../cash-flow-statement/` , `.../ratios/` |
| `/market/{sector}/` listing pages | `/stocks/industry/{industry}/` and the screener at `/screener/` |
| "N results, page X of Y" pagination | industry pages list constituents in one table (usually no pagination) |

The `Website` class ports almost directly: fetch → BeautifulSoup → strip
script/style/img/input → flatten every `<table>` to `Metric | Col1 | Col2 | ...` rows labeled
by nearest heading (`get_financial_text()`). The individual pipeline fetches ~4 pages per
company instead of 1 (overview + 3 statements) and concatenates them.

Rules: 1 s sleep between requests (keep), realistic User-Agent, respect robots.txt, and treat
markup changes as an expected failure mode (§9). Do not hammer: sector runs already cap at 100.

### 3.2 Authoritative structured source: SEC EDGAR (free, official, JSON)

Add `edgar_service.py` even in v1 — it is the fallback when scraping breaks and the source of
truth for verification:

- `https://www.sec.gov/files/company_tickers.json` — ticker → CIK mapping (cache locally).
- `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json` — every reported XBRL fact
  (revenue, net income, assets, equity...) with fiscal period tags.
- Requirements: `User-Agent: name (email)` header (put email in `.env` as `SEC_CONTACT_EMAIL`),
  max 10 req/s (our 1 s sleep is far under).

v1 uses EDGAR for: fiscal-year-end detection (§4.2), spot-verification of scraped numbers, and
as the Phase-5 fallback if stockanalysis.com blocks or changes. A later version can make EDGAR
primary (structured JSON → skip the LLM extraction step entirely for statements).

### 3.3 Sector membership

- Primary: stockanalysis.com industry pages (link extraction, like `get_sector_details`).
- Fallback: a committed static constituents file per index (e.g. S&P 500 / Russell 1000 CSV
  with ticker, company, GICS sector, GICS industry) refreshed manually. This also gives the
  pipeline a deterministic test mode with zero scraping.
- Sector taxonomy: use **GICS** names (11 sectors, industries below them) as the
  `sector_name` / `sub_sector` pair that Step 3 (KPI generation) receives.

### 3.4 Earnings calls (concall equivalent)

US earnings call transcripts are NOT on EDGAR. The Walk-the-Talk step keeps the exact same
two-path design:

- **Primary: Gemini Search grounding** — retarget the search prompt at: company IR page
  press releases, Motley Fool free transcripts (fool.com/earnings-call-transcripts),
  8-K earnings releases and 10-K/10-Q filings on sec.gov, investor-day presentations.
  Replace "BSE/NSE, screener.in, moneycontrol.com" with these.
- **Fallback: training-data synthesis** — identical, including the mandatory
  `⚠️ DATA SOURCE: LLM SYNTHESIS` disclaimer, `concall_source` flag
  (`gemini_search` / `llm_synthesis`), and LOW/HIGH Data Confidence banner in the scoring
  prompt. **Never remove this provenance plumbing.**
- transcript_scorer.py (RAG over user-supplied PDF transcripts) ports unchanged — US
  transcripts from IR pages are PDFs too.

### 3.5 Market data odds and ends

Market cap, P/E, price: present on stockanalysis.com overview page (scraped with the rest).
Optional: `yfinance` as a programmatic backup — if added, it is a new dependency requiring
explicit approval per repo policy.

---

## 4. Prompt Translation — India → US

All prompts keep their structure, guard blocks, checklists, self-checks, and fixed output
tables. Only domain references change. **Prompt edits are additive; guards are never removed.**

### 4.1 Mechanical substitutions (every prompt)

| India | US |
|---|---|
| ₹, Cr., "9 Crores", lakhs | $, millions (M) / billions (B) |
| screener.in | stockanalysis.com / SEC filings |
| BSE/NSE filings, moneycontrol.com | SEC EDGAR (10-K, 10-Q, 8-K), company IR pages |
| "Q1 FY25" (Apr–Jun) | "Q1 FY2025 (fiscal)" with company-specific quarter dating — see 4.2 |
| Regional Context: INDIA | Regional Context: UNITED STATES (SEC/GAAP reporting) |
| Rating agencies CRISIL, CARE, HDFC Securities | Moody's, S&P, sell-side research (same do-not-fabricate rule) |

### 4.2 Fiscal year handling — the most dangerous translation

Indian companies all end FY in March. US companies choose their own FYE (Apple ≈ late Sep,
Microsoft Jun 30, Nvidia ≈ end of Jan, Walmart Jan 31; most use Dec 31). Consequences:

- **Step 0 gains a task:** detect and store `fiscal_year_end` per company (from EDGAR
  companyfacts `fy`/`fp`/`end` tags, or the statements page column headers). Inject it into
  every downstream prompt as `**FISCAL YEAR END**: {fye}`.
- The **"CRITICAL DATA INSTRUCTION"** guard becomes: "All figures below, including the most
  recent fiscal year and quarters, are actual reported results, not projections. This
  company's fiscal year ends {fye}; 'FY2026' may therefore already be a reported period even
  though calendar 2026 is not over."
- The **Guidance Period Assignment** guard (the `Year/Period = target year, not call year`
  block with EXAMPLE + SELF-CHECK) carries over verbatim but the example becomes:
  "If management states a revenue target during the Q2 FY2025 call and the target is for
  FY2026, the row is labelled FY2026." Add: "Confirm which fiscal calendar the company uses
  before assigning periods — a January-FYE company's 'FY2026' is mostly calendar 2025."
- Walk-the-Talk window: FY20–FY25 → **FY2021–FY2026** (or "last 5 completed fiscal years"),
  computed from the company's own fiscal calendar.

### 4.3 Guard translations (keep the spirit, swap the trap)

| Indian guard | US replacement |
|---|---|
| "Revenue from Operations vs Total Income" (other income inflates top line) | "**Revenue / Net sales vs Total revenues**: use the GAAP revenue top line. Do NOT use 'Total revenues' when it bundles interest/other income (common for financials), and NEVER use non-GAAP 'adjusted revenue'." |
| (no equivalent) — NEW | "**GAAP vs non-GAAP**: US managements guide on adjusted/non-GAAP metrics (adjusted EBITDA, adjusted EPS). When comparing guidance to outcome, compare like-for-like: non-GAAP guidance against the company's own reported non-GAAP actual, and label the basis in the table." |
| Standalone vs consolidated statements | Not applicable (GAAP is consolidated) — drop silently. |
| (no equivalent) — NEW | "**Units integrity**: 10-K tables may be 'in thousands' or 'in millions'. State every figure with its unit; never mix scales in one comparison." |
| MOST RECENT PERIOD IDENTIFICATION (rightmost column = latest actual; reconcile standalone TTM vs table values; score the latest trend) | Verbatim, with a US example (e.g. Net income $670M FY2024 → $326M FY2026 = deteriorating; score FY2026). |
| Efficiency-ratio "report exact values, don't interpolate" | Verbatim. |
| PERIOD MISMATCH / UNVERIFIABLE integrity check in concall scoring | Verbatim. |
| Superlatives rule ("first in South India") | Verbatim with US flavor ("largest in North America"). |

### 4.4 Prompt inventory to port (10 system prompts + 8 user-prompt builders)

Sector: `DEFAULT_SYSTEM_PROMPT_SCREENER`, `_SCORE`, `_JSON` + `user_prompt_screener_sector`,
`user_prompt_score` (with TODAY'S DATE injection), `user_prompt_json`.
Individual: `DEFAULT_SYSTEM_PROMPT_SCREENER_IND`, `_JSON_IND`, `_KPI`, `_KPI_CAL`,
`_GEMINI_SEARCH`, `_FINAL`, `_CONCALL_SCORE` + `user_prompt_screener_ind`, `create_user_json`,
`user_prompts_kpi`, `user_prompts_gemini_search`, `user_prompts_kpi_cal`,
`create_user_prompt_final`, `user_prompt_walkthetalk` (synthesis), `user_prompt_walkthetalk_search`
(grounded), `prompt_concall_score` (with `{confidence_banner}` driven by `concall_source`).
Each gets a matching section in `prompts/sector_pipeline.md` / `prompts/individual_pipeline.md`.

---

## 5. Workflow Specs

### 5.1 Sector pipeline — 8 phases

| Phase | What it does | US adaptation |
|---|---|---|
| 1 | Fetch sector URL, read title + page count, create `Sector/{name}/` folder (sanitize `<>:"/\|?*;`) | Industry page on stockanalysis.com; page count usually 1 |
| 2 | Collect company links from listing pages (`/company/` prefix, 1 s sleep) | Collect `/stocks/{ticker}/` links; dedupe |
| 3 | Fetch each company page for its display name | Same; also capture ticker (needed for EDGAR + URLs) |
| 4 | Sector/sub-sector classification from a constituent's market links | Read GICS sector/industry off the company page (or the constituents file) |
| — | **Cache prompt**: if folder has files, pause and ask continue-with-cache vs delete | Unchanged |
| 5 | Per company (skip if `{Company}.txt` exists; cap 100 LLM calls): scrape page text → LLM reproduces all financial tables as plain text → save `{Company}.txt` | Scraped text = concatenated overview + 3 statement pages; same 100 KB write guard |
| 6 | Per company (skip if `_Score.txt` exists or source >20 KB): LLM scores 0–100 with 25/25/20/15/15 weights, TODAY'S DATE + most-recent-period guards → `{Company}_Score.txt` | Prompt translation only |
| 7 | Per `_Score.txt`: LLM converts to strict JSON `{company, sector, score, key_metrics, explanation}`; append to `progress.json` after EACH company (resumability) | Unchanged |
| 8 | Write `{sector}.json` + `{sector}.csv` (`company,score,Sector,url` sorted desc, utf-8-sig) | url = stockanalysis.com company URL |

### 5.2 Individual pipeline — 8 steps

| Step | What it does | US adaptation |
|---|---|---|
| 0 | Scrape company URL → `site_text` (structured tables), company name, sector, sub-sector; then cache prompt if any output files exist | Input = ticker or stockanalysis URL; + detect `fiscal_year_end` (§4.2); sector from GICS |
| 1 | Financial data extraction (LLM) → cached at `Sector/{industry}/{Company}.txt`; abort if >100 KB | Prompt translation; quarterly-results priority instruction keeps "last 4 quarters, label each, flag YoY/QoQ" |
| 2 | Text → structured JSON (CompanyInfo, KeyPoints, Highlights, ProsCons, P&L, BS, CF, Ratios); tolerate parse failure by storing raw | ₹→$; screener section names → statement page names |
| 3 | LLM proposes 8–12 sector ratios + 8–12 KPIs as strict JSON | Region = UNITED STATES; GICS sector/industry in |
| 4 | KPI values via **Gemini Search** (LTM/TTM priority, omit-if-not-found, cite source); **fallback** = calculate from Step-2 JSON with standard formulas; then a cleanup LLM pass → strict numeric JSON | Search targets: 10-K/10-Q, IR pages |
| 5 | Final analysis + 0–100 score (40/20/15/15/10), fixed 5-row score table, OVERALL = arithmetic sum, Buy/Hold/Sell → `Individual_Stocks/{Company}.txt` | All §4 guards |
| 6 | Walk the Talk: Gemini-Search-grounded guidance-vs-outcome table FY window, `concall_source` flag; fallback synthesis + disclaimer → `{Company}_concall.txt` | §3.4 sources; §4.2 fiscal window; NEW non-GAAP guard |
| 7 | Concall credibility score: period-integrity check, fixed category weights within year, time-decay across years, Data Confidence line, no Buy/Hold/Sell → `{Company}_concall_score.txt`; skip if concall file >100 KB | Prompt translation only |

Per-step default models (from `models.json` aliases): steps 1–4 `gemini-flash`(-lite for JSON),
step 5–6 `gemini-pro`, step 7 `gemini-flash`. Keep the alias indirection — model IDs live ONLY
in `models.json`, resolved by `llm_service.llm()` and each Streamlit `llm()` dispatcher.

### 5.3 Results documentation layer

- **File conventions (LAW):** in `Individual_Stocks/`, a `.txt` with no underscore in the stem
  = financial analysis; only `_concall.txt` and `_concall_score.txt` suffixes exist. Any other
  name corrupts classification. In `Sector/{industry}/`: `{Company}.txt` (extraction),
  `{Company}_Score.txt`, `progress.json`, `{sector}.csv`, `{sector}.json`.
- **Score extraction** (`individual_service.py`): multi-pass regexes over the LLM text —
  pass 1 "overall score ... N/100" lines, pass 2 JSON-style `"score": N` in first 30 lines,
  pass 3 composite-table row, pass 4 `| **Total** | ... | **N** |`. Credibility patterns
  additionally tolerate emoji/mojibake between label and number. **Port them verbatim.**
  New-format support = append a new pass at the END + dry-run proof that no previously
  extracted value changed. (The `dYY.` mojibake alternates only matter if legacy cp1252 files
  exist; in a fresh utf-8-only repo they are harmless dead branches — keep them anyway for
  pattern parity.) Always write files with `encoding="utf-8"` (CSV: `utf-8-sig`).
- **`scores.json`**: `{"overall_scores": {company: int}, "credibility_scores": {company: float}}`,
  regenerated by scanning `Individual_Stocks/`; combined score = mean of the two when both exist.
- **`Sector_Combined.csv`**: for each sector CSV, keep rows with
  `score >= floor(max_score/10)*10`, concat, columns exactly `company,score,Sector,url`.
- **Dashboards**: individual dashboard (scores table, tiers, signals, aligned/divergent views)
  and sector dashboard (combined CSV, per-sector aggregation) — read-only over the files above.
- **`prompts/*.md`**: every prompt documented in markdown, updated in the same commit as any
  prompt change.
- **CLAUDE.md files**: root operating manual (copy map, traps, quality bars, escalation) +
  per-folder architecture docs. Write them as the system is built, not after.

---

## 6. Build Plan — milestones with acceptance criteria

Order matters: each milestone is testable without paid LLM calls until M4.

**M0 — Scaffold (no network).** Repo, `.venv` (Python 3.12), `.gitignore`, `.env.template`,
`models.json` (same alias scheme), `config.py` (paths, `TIER_THRESHOLDS`, hard-fail on missing
model keys, `STOCK_HUB_ROOT` override), `llm_service.py` with `llm()` dispatcher +
`clean_and_parse_json` + `check_api_status`.
✅ `config.py` imports; `check_api_status` reports each configured key; unit tests for
`clean_and_parse_json` pass.

**M1 — Data acquisition layer.** `scraper_service.py` (Website class for stockanalysis.com:
`get_financial_text` table flattening, industry-page link extraction, ticker parsing) +
`edgar_service.py` (ticker→CIK, companyfacts fetch, fiscal-year-end detection) + static
constituents CSV fallback.
✅ Against 3 live companies with different FYEs (e.g. AAPL, MSFT, a Dec-31 name): financial
text < 100 KB, contains income statement/balance sheet/cash flow tables with year columns;
FYE detected correctly for all 3. Save the fetched HTML as `tests/fixtures/` for offline tests.

**M2 — Ported prompts + docs.** `prompts.py` with all 18 artifacts translated per §4;
`prompts/sector_pipeline.md` + `prompts/individual_pipeline.md`; `tools/prompt_audit.py`
(whitespace-normalized comparison across all copies).
✅ Audit script reports IN SYNC for everything; a checklist review confirms every guard block
from §4.3 present in the final text.

**M3 — Pipelines + Full App.** Port `pipeline_manager.py`, `sector_pipeline.py`,
`individual_pipeline.py`, routers, `main.py`, frontend. Keep cache prompts, SSE events,
progress.json resumability, all size/count guards.
✅ Uvicorn boots with zero traceback; `/api/health` 200; pipeline start endpoints validate
input and stream SSE (mock the LLM layer for this test — a `FAKE_LLM=1` env switch in
`llm_service` that returns canned outputs is worth building; it makes the whole system
testable for free forever).

**M4 — First real runs (PAID — needs explicit go-ahead).** One individual run end-to-end on a
well-known megacap; inspect all 3 output files; verify score extraction returns numbers;
verify `concall_source=gemini_search` (if synthesis fallback fired, fix grounding first).
Then one SMALL sector/industry (<15 companies).
✅ `{Company}.txt`, `_concall.txt`, `_concall_score.txt` all extract; sector CSV/JSON written;
`scores.json` has both top-level keys; combined CSV rows satisfy the floor rule; a hand-check
of 5 numbers in the extraction against the 10-K (via EDGAR) shows no unit/period errors.

**M5 — Data layer + dashboards + Streamlit twins.** `individual_service.py`,
`sector_service.py`, both Visualizations apps, both Streamlit pipeline apps (importing shared
services per §2, or duplicated + audited), `transcript_scorer.py`.
✅ Streamlit apps boot headless; every widget key is in a `DEFAULTS` dict; dashboards show
M4's real data; extraction dry-run over all generated files: 100% extract.

**M6 — Operating manual + skills.** Root CLAUDE.md (copy map, traps §9, quality bars,
escalation rules), per-folder CLAUDE.md, and if using Claude Code: `/prompt-sync`,
`/rerun-stock`, `/data-doctor` skill ports.
✅ A fresh agent given only the repo can answer "where do I change the concall weights and
what else must change" correctly from the docs.

**Calibration note (important, unique to the port):** absolute scores will NOT be comparable
to the Indian repo's scores — different market, sector norms, and KPI baselines. Treat the US
repo as a fresh scale. During M4/M5, run 5–10 well-understood companies (mix of obviously
strong and obviously weak) and sanity-check the ordering, not the absolute values, before
trusting the pipeline.

---

## 7. Environment

```powershell
# Windows, Python 3.12
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# requirements: fastapi, uvicorn, requests, beautifulsoup4, pandas, streamlit,
#               openai, google-genai, python-dotenv, plotly  (+ anthropic optional)
# .env: OPENAI_API_KEY, GOOGLE_API_KEY, ANTHROPIC_API_KEY (opt), SEC_CONTACT_EMAIL

cd "Full App"; ..\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
curl -s http://localhost:8000/api/health
streamlit run individual\IndividualStockApp.py --server.headless true
```

---

## 8. Testing Strategy

1. **Offline fixtures first.** Commit saved HTML pages + EDGAR JSON under `tests/fixtures/`;
   scraper unit tests parse fixtures, never the live site. Add one "markup drift" canary test
   that runs live behind an env flag and asserts table count / column headers.
2. **FAKE_LLM mode.** `llm_service` env switch returning canned step outputs (a real saved
   response per step). Lets the full pipeline, SSE flow, caching, file writing, and extraction
   run in CI at zero cost.
3. **Extraction golden tests.** Every real LLM output file ever generated doubles as a test
   fixture: `test_extraction_regression` asserts extracted scores over the whole
   `Individual_Stocks/` + `Sector/` tree never change when regexes are touched (append-only rule,
   enforced).
4. **Structural invariants** (run as tests and inside `/data-doctor`): scores.json parses with
   both keys; combined CSV schema + floor rule; filename conventions (no illegal underscores);
   every `{Company}.txt` in Individual_Stocks has extractable score; every `_concall.txt`
   either search-grounded or carries the synthesis disclaimer.
5. **Prompt-parity audit** (`tools/prompt_audit.py`): whitespace-normalized diff of every
   prompt/threshold copy; run pre-commit and in CI. This IS the port of `/prompt-sync audit`.
6. **Paid verification runs are deliberate.** Never run a pipeline "just to test". The accepted
   verification cost is ONE individual-company rerun (with cache deletion) after a prompt
   change, recording before → after score in the commit body.
7. **Cache-invalidation discipline.** After any prompt change, delete the affected cache files
   before the verification run — otherwise Step 1/Phases 5–6 read cache and the change is
   silently untested ("Cache Mirage").

---

## 9. Error-Resolution Playbook

Ordered diagnosis rules — port these into the new CLAUDE.md.

### Scraping / data acquisition
- **0 company links / empty tables / page count wrong** → site markup changed or bot-blocked
  (stockanalysis.com may serve JS-rendered or challenge pages). Save the fetched HTML as
  evidence; check status code and whether tables exist in raw HTML; report which selector
  broke. Do NOT speculatively rewrite the Website class. If blocked: back off, then switch
  that phase to the EDGAR/constituents fallback.
- **Step 1 output > 100 KB** → the guard aborts by design. Diagnose the scrape (nav junk, peer
  tables, JS payload leaking into `get_financial_text()`); never raise the limit.
- **Wrong-looking numbers** → verify against EDGAR companyfacts before touching anything;
  distinguish scrape error vs LLM extraction error vs units error (thousands/millions).
- **EDGAR 403/429** → User-Agent header missing/malformed or rate exceeded; fix headers,
  don't retry-loop.

### LLM / scoring
- **Score won't extract from an output file** → inspect the file; if the LLM used a new
  format, APPEND a regex pass; never edit existing passes; rerun the golden extraction test.
- **Score looks wrong (misread data: projection-vs-actual, wrong FY, non-GAAP vs GAAP, total
  revenues as revenue)** → the fix is a strengthened prompt guard (additive, loud
  `**CRITICAL (non-negotiable)**` block with EXAMPLE + SELF-CHECK, appended not woven in),
  NOT Python. Then: delete cache → one-company rerun → record before/after.
- **Concall score looks wrong** → FIRST check `{Company}_concall.txt` for the synthesis
  disclaimer. If present, the run was un-grounded: fix is rerunning with search grounding,
  not editing prompts.
- **Gemini Search fails (Step 4/6)** → fallbacks fire by design; verify `concall_source`,
  disclaimer, and confidence banner survived. A credibility score without provenance is worse
  than no score.
- **JSON phase fails to parse** → `clean_and_parse_json` already strips fences; if a model
  chronically emits invalid JSON, switch that step's model alias, don't loosen the parser
  silently.
- **Pipeline "change had no effect"** → Cache Mirage; delete cache files and rerun.

### Data layer / dashboards
- **Wrong dashboard number** → trace file → extraction pass → scores.json → endpoint/UI;
  report the FIRST divergent link; never patch downstream, never hand-edit output files.
- **Company missing from a view** → extraction returned None (new format → append pass) or a
  filename violates the underscore convention.
- **Frontend panel blank after backend change** → a router JSON key was renamed; grep
  `index.html` for every key you touched.

### Always stop and ask the user before
Changing any frozen constant in §1; removing/weakening a prompt guard; deleting output data
beyond one company being rerun; editing `.env`/`models.json` IDs; adding a dependency;
starting a sector run (cost); raising the 100-call/100 KB limits.

---

## 10. Open Decisions (resolve before M1)

1. **Universe** — S&P 500 only, Russell 1000, or all US listed? (Drives the constituents
   fallback file and how big sector runs get; >100-company sectors need multiple capped runs.)
2. **Primary source stance** — scrape-first (max parity with the Indian repo, fastest port) vs
   EDGAR-first (more robust/legal-proof, but Phase 5/Step 1 becomes a formatter instead of an
   LLM extraction and diverges from the original design). This plan assumes scrape-first with
   EDGAR verification.
3. **Streamlit twins: import-shared or duplicated?** Recommended: import-shared (§2). If
   duplicated for parity with the original repo, the prompt-audit script is mandatory from M2.
4. **New repo location/name** and whether output data is committed (the Indian repo commits it;
   recommended: yes, in separate data-churn commits).
