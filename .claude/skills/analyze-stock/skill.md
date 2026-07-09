---
name: analyze-stock
description: Analyze one or more Indian stocks by spawning parallel Claude research agents. Each agent does live web research, financial scoring (0-100), Walk the Talk credibility analysis (FY21-FY26), and concall scoring (0-100). Use when asked to analyze a stock, score a company, run stock analysis, or compare rating agencies / any Indian listed company.
---

Analyze Indian stocks by spawning one parallel Claude agent per company. Each agent uses live web search to gather financial data (FY22–FY26), applies the 5-dimension scoring framework, builds a Walk the Talk table, and computes a concall credibility score. No scripts are modified; no Apps_link pipeline is invoked.

All paths below are relative to `D:\stocks\Apps_link\`.

## Usage

```
/analyze-stock <COMPANY NAME(S)>
```

Examples:
- `/analyze-stock CRISIL Ltd`
- `/analyze-stock HDFC Bank`
- `/analyze-stock CRISIL Ltd, CARE Ratings Ltd, ICRA Ltd`

Multiple companies → spawn all agents in parallel in a single message.

## Run (agent path)

For each company in the user's input, spawn one Agent with the prompt template below (substituting `{{COMPANY}}`). Launch all agents in **one** message so they run in parallel.

```
Agent({
  description: "{{COMPANY}} — full financial + concall analysis",
  prompt: <see AGENT PROMPT TEMPLATE below>
})
```

After all agents return, compile the Final Scores Table, then execute the **HTML Output** section below.

---

## Agent Prompt Template

Replace `{{COMPANY}}` with the full company name (e.g. "CRISIL Ltd", "HDFC Bank Ltd").

```
You are a senior equity research analyst. Analyze **{{COMPANY}}** (Indian listed company) using live web search.
Cover FY2022–FY2026 (5 years) plus the most recent 4 quarters. Today is {today's date}.

## TASK 1 — FINANCIAL ANALYSIS & SCORE (0–100)

Search for {{COMPANY}}'s financials from the following approved sources **only**, in priority order:

1. **Screener.in** (PRIMARY) — financial statements, ratios, peer comparison, 10-year data
2. **NSE/BSE filings** — quarterly results announcements, annual reports, investor presentations (nseindia.com, bseindia.com)
3. **Moneycontrol** (moneycontrol.com) — financials, ratios, earnings summaries
4. **Trendlyne** (trendlyne.com) — KPIs, DVM scores, estimates (note: some pages require login — use only what is publicly accessible)
5. **Economic Times Markets** (economictimes.indiatimes.com/markets) — earnings news, analyst commentary, results coverage
6. **Value Research Online** (valueresearchonline.com) — financial data, stock fundamentals
7. **Kotak Securities** (kotaksecurities.com) — research notes, stock data where publicly available

Do NOT use Tickertape, Groww, Zerodha, StockAnalysis, or any source not listed above.

Extract:
- P&L (FY22–FY26): Revenue from Operations, EBITDA, EBITDA Margin %, PAT, PAT Margin %, EPS
- Quarterly (last 4 Q): label each (e.g. Q1 FY26, Q4 FY25) — Revenue, EBIT, PAT, QoQ change, YoY change
- Balance Sheet: Total Assets, Net Worth/Equity, Debt, Cash & equivalents
- Cash Flow: Operating CF, Free CF
- Ratios: ROE, ROCE, P/E, P/B, Dividend yield, Debt/Equity, Asset Turnover

Identify the sector, then select 8–12 most relevant Sector KPIs (e.g. for Banking: NIM, GNPA,
CASA ratio; for IT: Revenue per employee, attrition, utilisation; for FMCG: volume growth,
gross margin; for CRAs: market share, ratings volume growth, non-ratings revenue %).

**CRITICAL DATA RULES:**
- Revenue = Revenue from Operations (NOT Total Income)
- Annual growth = from full-year P&L only, never a single quarter's YoY
- Efficiency ratios = exact values from Ratios section of filings

**Scoring methodology (0–100):**
- KPI & Ratio Benchmark Performance: 40%
- Financial Performance (P&L trends): 20%
- Growth Trajectory: 15%
- Financial Health & Stability: 15%
- Valuation Assessment: 10%

Output:
```
OVERALL SCORE: [X/100]
```
Then: detailed breakdown by dimension, key metrics table, top 3–4 strengths, risk factors,
Investment Decision (Buy/Hold/Sell with rationale).

## TASK 2 — WALK THE TALK ANALYSIS (FY21–FY26)

Search earnings call transcripts, concall notes, annual report MD&A, and investor presentations
for {{COMPANY}} from FY2021 to FY2026. Use these approved sources only:
- **Screener.in** — concall notes/transcripts if listed
- **NSE/BSE filings** — investor presentations, earnings release documents, AGM material
- **Moneycontrol** — earnings call summaries, management commentary, results analysis
- **Trendlyne** — concall transcripts where publicly accessible (skip login-gated pages)
- **Economic Times Markets** — earnings call coverage, CFO/CEO quotes, results commentary
- **Value Research Online** — MD&A summaries, management discussion excerpts
- **Kotak Securities** — research reports with management guidance quotes (public pages only)

Create this table:

| Year/Period | Management Guidance (Quantitative) | Actual Outcome | Indicator |
|---|---|---|---|

Indicator: ✅✅ Overachieved | ✅ Achieved | 🟡 Nearly Met | ❌ Missed

**CRITICAL RULES:**
- Year/Period = fiscal year the TARGET applies to, NOT when the call was held
- Revenue = Revenue from Operations only
- Annual growth from full-year P&L

Cover: revenue growth targets, margin guidance, strategic initiative timelines (new products,
acquisitions, expansions), capex commitments, hiring/headcount plans, regulatory milestones.

After the table: overall credibility trend, management communication quality, investment implications.

## TASK 3 — CONCALL CREDIBILITY SCORE (0–100)

Score each row from the Walk the Talk table:
- Overachieved (>105% of guidance): 100 pts
- Achieved (95–105%): 85 pts
- Nearly Met (85–94%): 60 pts
- Missed (<85%): 30 pts

Weights: Revenue Guidance 30% | EBITDA/Margin 25% | Strategic Initiatives 20% |
New Products/Digital 15% | Other 10%

Apply time decay: FY26 weight 1.5x, FY25 1.25x, FY24 1.0x, FY23 0.8x, FY22 0.65x.

Output:
```
CREDIBILITY SCORE: [X/100]
```
With interpretation (Exceptional 85–100 / Strong 70–84 / Moderate 55–69 / Weak 40–54 / Poor <40)
and top 3 credibility observations.

## FINAL OUTPUT FORMAT

End your response with this exact block:

```
=== SCORES ===
COMPANY: {{COMPANY}}
SECTOR: [sector name, e.g. Banking / IT / FMCG / Capital Markets]
FINANCIAL SCORE: [number]/100
CONCALL SCORE: [number]/100
COMBINED SCORE: [number]/100
SIGNAL: [Strong Buy / Moderate Buy / Hold / Avoid]
=== END SCORES ===
```
```

---

## Signal Classification (from pipeline logic)

After agents return, apply this classification to display the pipeline signal:

| Condition | Signal |
|---|---|
| Financial ≥ 75 AND Concall ≥ 75 | Strong Buy |
| Financial ≥ 75 AND Concall < 60 | Financials Strong, Concall Weak |
| Concall ≥ 75 AND Financial < 60 | Concall Strong, Financials Weak |
| Financial ≥ 60 AND Concall ≥ 60 | Moderate Buy |
| Financial < 50 AND Concall < 50 | Avoid |
| Otherwise | Mixed |

---

## Output Format (display after all agents return)

### 1. Final Scores Table

| Company | Sector | Financial Score | Concall Score | Combined Score | Signal |
|---|---|---|---|---|---|
| {{COMPANY}} | ... | X/100 | X/100 | X/100 | ... |

### 2. Walk the Talk Summary

For each company, show a condensed 3-row version of the Walk the Talk table (most recent 3 years).

### 3. Key Differentiators

Side-by-side table comparing: market position, P/E, EBITDA margin, ROE, key strategic bet, credibility gap.

### 4. Ranking & Verdict

Rank companies by Combined Score. For each: Combined score, brief "why" in 1–2 sentences.

---

## HTML Output (run AFTER displaying results to user)

After showing results to the user, perform these file-writing steps using the Write and PowerShell tools.

### Step 1 — Ensure output directory exists

```powershell
New-Item -ItemType Directory -Force "D:\stocks\Apps_link\ClaudeAnalysis"
```

### Step 2 — Write individual HTML report for each company

For each company analyzed in this run, write a file:
`D:\stocks\Apps_link\ClaudeAnalysis\{SafeCompanyName}_{YYYYMMDD_HHMMSS}.html`

Where `{SafeCompanyName}` = company name with spaces replaced by underscores and special chars removed (e.g. `CRISIL_Ltd_20260626_143022`). Use the actual run timestamp (today's date + current time).

The individual report HTML template:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{COMPANY} — Stock Analysis Report</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }
  .header { background: linear-gradient(135deg, #1e293b, #0f172a); padding: 2rem; border-bottom: 1px solid #334155; }
  .header h1 { font-size: 2rem; font-weight: 700; color: #f1f5f9; }
  .header .meta { color: #94a3b8; margin-top: 0.5rem; font-size: 0.9rem; }
  .sector-badge { display: inline-block; background: #1d4ed8; color: #bfdbfe; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; margin-top: 0.5rem; }
  .score-cards { display: flex; gap: 1rem; padding: 1.5rem 2rem; flex-wrap: wrap; }
  .score-card { flex: 1; min-width: 160px; background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; text-align: center; }
  .score-card .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 0.5rem; }
  .score-card .value { font-size: 2.25rem; font-weight: 800; }
  .score-card.financial .value { color: #3b82f6; }
  .score-card.concall .value { color: #8b5cf6; }
  .score-card.combined .value { color: #10b981; }
  .signal-banner { margin: 0 2rem 1.5rem; padding: 1rem 1.5rem; border-radius: 10px; font-size: 1.1rem; font-weight: 700; text-align: center; }
  .signal-strong-buy { background: #14532d; color: #86efac; border: 1px solid #16a34a; }
  .signal-moderate-buy { background: #164e63; color: #67e8f9; border: 1px solid #0891b2; }
  .signal-hold { background: #78350f; color: #fcd34d; border: 1px solid #d97706; }
  .signal-avoid { background: #450a0a; color: #fca5a5; border: 1px solid #dc2626; }
  .signal-mixed { background: #1e1b4b; color: #c4b5fd; border: 1px solid #7c3aed; }
  .section { padding: 1.5rem 2rem; border-top: 1px solid #1e293b; }
  .section h2 { font-size: 1.1rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1rem; }
  .content { background: #1e293b; border-radius: 10px; padding: 1.25rem; line-height: 1.7; white-space: pre-wrap; font-size: 0.9rem; color: #cbd5e1; }
  table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  th { background: #1e293b; color: #94a3b8; padding: 0.75rem 1rem; text-align: left; font-weight: 600; border-bottom: 2px solid #334155; }
  td { padding: 0.75rem 1rem; border-bottom: 1px solid #1e293b; color: #cbd5e1; }
  tr:hover td { background: #1e293b; }
  .indicator-over { color: #34d399; }
  .indicator-achieved { color: #6ee7b7; }
  .indicator-near { color: #fbbf24; }
  .indicator-missed { color: #f87171; }
  .footer { padding: 1.5rem 2rem; color: #475569; font-size: 0.8rem; border-top: 1px solid #1e293b; }
  .back-link { display: inline-block; margin: 0 2rem 1rem; color: #3b82f6; text-decoration: none; font-size: 0.9rem; }
  .back-link:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="header">
  <a class="back-link" href="index.html">← Back to Dashboard</a>
  <h1>{COMPANY}</h1>
  <div class="meta">Analysis Date: {DATE} &nbsp;|&nbsp; Report generated by Claude</div>
  <span class="sector-badge">{SECTOR}</span>
</div>

<div class="score-cards">
  <div class="score-card financial">
    <div class="label">Financial Score</div>
    <div class="value">{FINANCIAL_SCORE}</div>
    <div style="color:#64748b;font-size:0.8rem;margin-top:0.25rem;">/100</div>
  </div>
  <div class="score-card concall">
    <div class="label">Concall Score</div>
    <div class="value">{CONCALL_SCORE}</div>
    <div style="color:#64748b;font-size:0.8rem;margin-top:0.25rem;">/100</div>
  </div>
  <div class="score-card combined">
    <div class="label">Combined Score</div>
    <div class="value">{COMBINED_SCORE}</div>
    <div style="color:#64748b;font-size:0.8rem;margin-top:0.25rem;">/100</div>
  </div>
</div>

<div class="signal-banner signal-{SIGNAL_CLASS}">{SIGNAL}</div>

<div class="section">
  <h2>Financial Analysis</h2>
  <div class="content">{FINANCIAL_ANALYSIS_TEXT}</div>
</div>

<div class="section">
  <h2>Walk the Talk — Management Credibility (FY21–FY26)</h2>
  <div style="overflow-x:auto">
  {WALK_THE_TALK_TABLE}
  </div>
</div>

<div class="section">
  <h2>Concall Credibility Analysis</h2>
  <div class="content">{CONCALL_ANALYSIS_TEXT}</div>
</div>

<div class="footer">
  Generated by /analyze-stock skill &nbsp;|&nbsp; {DATE} &nbsp;|&nbsp; Data sources: Screener.in · NSE/BSE filings · Moneycontrol · Trendlyne · ET Markets · Value Research Online · Kotak Securities
</div>
</body>
</html>
```

**Filling template placeholders:**
- `{COMPANY}` — company name
- `{SECTOR}` — sector from scores block
- `{DATE}` — current date as `DD MMM YYYY` (e.g. `26 Jun 2026`)
- `{FINANCIAL_SCORE}`, `{CONCALL_SCORE}`, `{COMBINED_SCORE}` — numbers only (no `/100`)
- `{SIGNAL}` — signal text (e.g. `Strong Buy`)
- `{SIGNAL_CLASS}` — CSS class key: `strong-buy` / `moderate-buy` / `hold` / `avoid` / `mixed` (lowercase, hyphenated, matching the `signal-*` CSS classes above; for multi-word signals like "Financials Strong, Concall Weak" use `mixed`)
- `{FINANCIAL_ANALYSIS_TEXT}` — full Task 1 output text (escape `<`, `>`, `&` as HTML entities)
- `{WALK_THE_TALK_TABLE}` — HTML `<table>` built from the Walk the Talk rows; use `<td class="indicator-over">✅✅</td>` etc. for indicator column
- `{CONCALL_ANALYSIS_TEXT}` — full Task 3 output text (escape HTML entities)

### Step 3 — Update master registry JSON

Read `D:\stocks\Apps_link\ClaudeAnalysis\registry.json` if it exists (empty array `[]` if not). It holds one object per company (keyed by company name). Update or insert an entry for each company analyzed in this run:

```json
[
  {
    "company": "CRISIL Ltd",
    "sector": "Capital Markets",
    "financial_score": 78,
    "concall_score": 72,
    "combined_score": 75,
    "signal": "Strong Buy",
    "last_analyzed": "2026-06-26",
    "report_file": "CRISIL_Ltd_20260626_143022.html"
  }
]
```

- If a company already exists in the array, replace its entry (match by `company` name, case-insensitive).
- `report_file` = the filename (not full path) of the individual HTML written in Step 2.
- Write the updated array back to `registry.json`.

### Step 4 — Rebuild master index.html

Read `registry.json` (now updated) and write `D:\stocks\Apps_link\ClaudeAnalysis\index.html` using the template below. Sort rows by `combined_score` descending.

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Analysis Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }
  .header { background: linear-gradient(135deg, #1e293b, #0f172a); padding: 2rem; border-bottom: 1px solid #334155; }
  .header h1 { font-size: 1.75rem; font-weight: 700; color: #f1f5f9; }
  .header p { color: #64748b; margin-top: 0.4rem; font-size: 0.9rem; }
  .stats { display: flex; gap: 1rem; padding: 1.25rem 2rem; flex-wrap: wrap; border-bottom: 1px solid #1e293b; }
  .stat { background: #1e293b; border-radius: 8px; padding: 0.75rem 1.25rem; min-width: 120px; }
  .stat .n { font-size: 1.5rem; font-weight: 800; color: #38bdf8; }
  .stat .l { font-size: 0.75rem; color: #64748b; margin-top: 0.1rem; }
  .table-wrap { padding: 1.5rem 2rem; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  th { background: #1e293b; color: #94a3b8; padding: 0.75rem 1rem; text-align: left; font-weight: 600; border-bottom: 2px solid #334155; white-space: nowrap; }
  td { padding: 0.75rem 1rem; border-bottom: 1px solid #1e293b; vertical-align: middle; }
  tr:hover td { background: #1a2234; }
  .company-link { color: #60a5fa; text-decoration: none; font-weight: 600; }
  .company-link:hover { text-decoration: underline; }
  .sector-tag { display: inline-block; background: #1e3a5f; color: #93c5fd; padding: 0.2rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; }
  .score-pill { display: inline-block; padding: 0.25rem 0.6rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem; min-width: 3rem; text-align: center; }
  .score-hi { background: #14532d; color: #86efac; }
  .score-mid { background: #164e63; color: #67e8f9; }
  .score-low { background: #450a0a; color: #fca5a5; }
  .signal-pill { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 700; white-space: nowrap; }
  .sig-sb { background: #14532d; color: #86efac; }
  .sig-mb { background: #164e63; color: #67e8f9; }
  .sig-ho { background: #78350f; color: #fcd34d; }
  .sig-av { background: #450a0a; color: #fca5a5; }
  .sig-mx { background: #1e1b4b; color: #c4b5fd; }
  .date-col { color: #64748b; font-size: 0.8rem; white-space: nowrap; }
  .footer { padding: 1.25rem 2rem; color: #475569; font-size: 0.8rem; border-top: 1px solid #1e293b; }
  .updated { color: #475569; font-size: 0.8rem; padding: 0 2rem 1rem; }
</style>
</head>
<body>
<div class="header">
  <h1>Stock Analysis Dashboard</h1>
  <p>Indian equities scored on financial performance + management credibility</p>
</div>

<div class="stats">
  <div class="stat"><div class="n">{TOTAL_COUNT}</div><div class="l">Companies Tracked</div></div>
  <div class="stat"><div class="n">{STRONG_BUY_COUNT}</div><div class="l">Strong Buy</div></div>
  <div class="stat"><div class="n">{MOD_BUY_COUNT}</div><div class="l">Moderate Buy</div></div>
  <div class="stat"><div class="n">{AVOID_COUNT}</div><div class="l">Avoid</div></div>
</div>

<div class="updated">Last updated: {LAST_UPDATED}</div>

<div class="table-wrap">
<table>
  <thead>
    <tr>
      <th>#</th>
      <th>Company</th>
      <th>Sector</th>
      <th>Financial</th>
      <th>Concall</th>
      <th>Combined</th>
      <th>Signal</th>
      <th>Analyzed</th>
    </tr>
  </thead>
  <tbody>
{TABLE_ROWS}
  </tbody>
</table>
</div>

<div class="footer">
  Powered by /analyze-stock skill &nbsp;|&nbsp; Claude Sonnet &nbsp;|&nbsp; Data: Screener.in · NSE/BSE filings · Moneycontrol · Trendlyne · ET Markets · Value Research Online · Kotak Securities
</div>
</body>
</html>
```

**Building `{TABLE_ROWS}`** — for each entry in the registry (sorted by combined_score desc), emit:

```html
    <tr>
      <td style="color:#475569;font-weight:700">{RANK}</td>
      <td><a class="company-link" href="{REPORT_FILE}">{COMPANY}</a></td>
      <td><span class="sector-tag">{SECTOR}</span></td>
      <td><span class="score-pill {SCORE_CLASS_FIN}">{FINANCIAL_SCORE}</span></td>
      <td><span class="score-pill {SCORE_CLASS_CON}">{CONCALL_SCORE}</span></td>
      <td><span class="score-pill {SCORE_CLASS_COM}">{COMBINED_SCORE}</span></td>
      <td><span class="signal-pill {SIG_CLASS}">{SIGNAL}</span></td>
      <td class="date-col">{LAST_ANALYZED}</td>
    </tr>
```

Score pill class: `score-hi` if ≥ 70, `score-mid` if 50–69, `score-low` if < 50.
Signal pill class: `sig-sb` = Strong Buy, `sig-mb` = Moderate Buy, `sig-ho` = Hold, `sig-av` = Avoid, `sig-mx` = anything else (Mixed / Financials Strong Concall Weak / etc).

**Stats block values:**
- `{TOTAL_COUNT}` = total entries in registry
- `{STRONG_BUY_COUNT}` = count where signal == "Strong Buy"
- `{MOD_BUY_COUNT}` = count where signal == "Moderate Buy"
- `{AVOID_COUNT}` = count where signal == "Avoid"
- `{LAST_UPDATED}` = current date + time (e.g. `26 Jun 2026, 14:30`)

After writing both files, tell the user:
> Reports saved to `D:\stocks\Apps_link\ClaudeAnalysis\`. Open `index.html` in a browser to view the dashboard.

---

## Gotchas

- **CRISIL uses CY (Jan–Dec) fiscal year**, not Indian Apr–Mar FY — label accordingly when comparing with ICRA/CARE
- **Management rarely gives quantitative guidance** — Indian CRAs explicitly refuse; use directional commentary and strategic targets instead
- **PAT can be suppressed by one-time items** (acquisition amortisation, impairments, tax normalisations) — score on underlying/operating PAT where material
- **Gemini/external APIs are NOT used** — all analysis is done by the Claude agent via web search; no pipeline scripts are invoked
- **Do not modify any file** in `Apps_link/` — read-only reference to understand the scoring framework if needed, never execute or change pipeline scripts
- **Multiple companies → one message** with all Agent calls in parallel, not sequential
- **HTML escaping** — when inserting analysis text into HTML `<div class="content">`, escape `<` → `&lt;`, `>` → `&gt;`, `&` → `&amp;` so the pre-wrap display is correct
- **registry.json update** — always read first, then upsert (don't overwrite the whole file with only the current run's companies)

## Troubleshooting

- **Agent returns N/A scores**: The `=== SCORES ===` block is missing — ask the agent to reformat its output
- **Score seems too high/low**: Check whether the agent used Revenue from Operations (not Total Income) and full-year figures (not quarterly YoY as annual)
- **Concall data sparse**: If earnings call transcripts are unavailable for a company, the agent should use MD&A sections from annual reports and investor presentations; flag as "limited transcript data"
- **index.html not updating**: Verify `registry.json` was written successfully before rebuilding the index
