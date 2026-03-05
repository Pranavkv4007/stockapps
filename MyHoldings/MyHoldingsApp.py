"""
MyHoldings — Streamlit Portfolio Analysis App
Tracks personal holdings, runs analysis pipelines, and displays a unified portfolio dashboard.
"""

# ============================================================================
# Section 0 — Imports, sys.path setup, constants
# ============================================================================
import streamlit as st
import os
import sys
import json
import time
import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Setup paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
FULL_APP_DIR = os.path.join(PROJECT_ROOT, "Full App")
HOLDINGS_FILE = os.path.join(BASE_DIR, "holdings.json")
INDIVIDUAL_STOCKS_DIR = os.path.join(PROJECT_ROOT, "Individual_Stocks")
SECTOR_DIR = os.path.join(PROJECT_ROOT, "Sector")

os.makedirs(INDIVIDUAL_STOCKS_DIR, exist_ok=True)

# Add Full App to sys.path for imports
if FULL_APP_DIR not in sys.path:
    sys.path.insert(0, FULL_APP_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

# Import backend services from Full App
from backend.config import (
    OPENAI_MODEL, GPT4O, GEMINI_MODEL, MODEL_OPTIONS,
    TIER_THRESHOLDS, SIGNAL_COLORS,
)
from backend.services.llm_service import (
    llm, gemini_llm_kpi, clean_and_parse_json, clean_text_for_llm,
    get_openai_client, get_gemini_client,
)
from backend.services.scraper_service import (
    Website, get_subsector_details, get_sector_names,
)
from backend.services.individual_service import (
    extract_overall_score, extract_credibility_score,
    assign_tier, assign_signal,
)
from backend.services.prompts import (
    DEFAULT_SYSTEM_PROMPT_SCREENER as SECTOR_SP_SCREENER,
    DEFAULT_SYSTEM_PROMPT_SCORE,
)

# Individual prompts — import from IndividualStockApp directly since prompts.py
# only has sector prompts. We define them inline (copied from IndividualStockApp.py).
from backend.services.prompts import (
    DEFAULT_SYSTEM_PROMPT_SCREENER,
)

# ============================================================================
# Section 0b — Individual Pipeline Prompts (from IndividualStockApp.py)
# ============================================================================

SP_SCREENER = """
You are a specialized financial data extraction AI designed to process scraped text from screener websites and extract comprehensive financial information. Your primary objective is to parse unstructured financial text and reproduce it in the exact same format and presentation style as it appears on the screener website.

Begin with a concise checklist (3-7 bullets) of what you will do; keep items conceptual, not implementation-level.

**Core Responsibilities**
- Extract ALL available financial data from the provided text without omission.
- Maintain the exact formatting, layout, and presentation style of the original screener website.
- Preserve tables, headings, subheadings, and hierarchical structure.
- Keep original numerical formats, units, and styling (9 Crores, percentages, etc.).
- Maintain the same grouping and categorization as shown on screener.

**Extraction Categories** (maintain original screener formatting):
1. **Company Summary:** Exactly as displayed on screener, with the same layout.
2. **Key Financial Highlights:** Preserve table format and metric groupings.
3. **Balance Sheet:** Maintain the exact table structure with years/periods as columns.
4. **Cash Flow Statement:** Keep the same format with proper indentation and grouping.
5. **Profit & Loss Statement:** Preserve the hierarchical structure and calculations.
6. **Financial Ratios:** Maintain categorization and table format as shown.

**Formatting Rules**
- Reproduce exact table structures with proper alignment.
- Keep original headings, subheadings, and section breaks.
- Maintain indentation levels for sub-items.
- Preserve number formatting (commas, decimal places, units).
- Keep the same time period labels and column headers.
- Reproduce any charts or graphical data descriptions exactly, if present.
- Maintain color coding descriptions if mentioned in text.

**Data Handling**
- Extract data exactly as presented, including any calculated fields.
- Keep the same order of items as they appear on screener.
- Preserve any footnotes, disclaimers, or additional notes.
- Maintain the same level of detail and granularity.
- Keep any percentage changes and growth rates in original format.

**Output Format**
- Present data in plain text format, matching screener's visual layout.
- Use appropriate spacing and alignment to recreate tables.
- Include all section headers and subheaders.
- Maintain the flow and sequence of information as on screener.
- Preserve any special formatting or emphasis used in original.

After producing your output, validate that all listed extraction categories and formatting rules have been adhered to. If any item is missing or the output deviates from screener's format, revise accordingly before presenting the final result.
"""

SP_JSON = """
You are a highly skilled financial data structuring assistant.
Your task is to transform raw scraped financial data from sources such as Screener.in
into a clean, structured, and comprehensive JSON format.

Rules:
1. Preserve all information — do not omit any financial metrics, qualitative points, ratios, or textual descriptions.
2. Categorize data into these sections:
   - CompanyInfo (name, ticker symbols, website, about section)
   - KeyPoints (business highlights)
   - KeyFinancialHighlights (market cap, P/E, ROE, etc.)
   - ProsAndCons (separate 'Pros' and 'Cons')
   - ProfitAndLossStatement (table by year)
   - BalanceSheet (table by year)
   - CashFlowStatement (table by year)
   - Ratios (table by year)
3. Keep original figures with units (₹, %, Cr., etc.).
4. Tables must have proper year-wise mapping.
5. Output valid JSON with each section containing all relevant fields.
6. If a data point is missing, insert "null" but keep the field name.
7. Include both qualitative and quantitative details exactly as in the input.
8. Avoid assumptions — only use what is explicitly present.
"""

SP_KPI = """
You are a senior financial analyst and sector specialist with deep expertise in industry-specific financial analysis. You understand how different business models, regulatory environments, and operational characteristics require tailored analytical frameworks.

Your task is to analyze the provided sector and determine the most critical financial ratios and Key Performance Indicators (KPIs) that are essential for evaluating companies in that specific sector.

SELECTION CRITERIA:
- Choose ratios and KPIs that are most commonly used by equity analysts, credit analysts, and institutional investors for the sector
- Include metrics that capture the sector's unique business model characteristics
- Focus on indicators that reflect operational efficiency, financial health, and competitive positioning
- Consider regulatory requirements and industry standards where applicable
- Ensure metrics are calculable from standard financial statements and company disclosures

RATIO SELECTION GUIDELINES:
- Include fundamental profitability, liquidity, leverage, and efficiency ratios
- Add sector-specific financial ratios that capture unique aspects of the business
- Focus on ratios that help assess financial stability and performance trends
- Minimum 8 ratios, maximum 12 ratios

KPI SELECTION GUIDELINES:
- Include operational metrics that drive financial performance in the sector
- Focus on customer, growth, efficiency, and quality indicators
- Choose KPIs that are regularly reported by companies and tracked by analysts
- Include both leading and lagging indicators
- Minimum 8 KPIs, maximum 12 KPIs

CRITICAL OUTPUT REQUIREMENT:
You must respond ONLY with a valid JSON object in this EXACT format with no additional text, explanations, or formatting:

{
  "Sector": "sector_name",
  "Ratios": [
    "ratio1",
    "ratio2"
  ],
  "KPI": [
    "kpi1",
    "kpi2"
  ]
}

Do not include any explanations, comments, or additional text outside the JSON object.
"""

SP_KPI_CAL = """Developer: # Role and Objective
You are a specialist in calculating financial ratios and KPIs. Your primary function is to compute ratios and KPIs solely when all required data is reliably provided via  financial summary.

Begin with a concise checklist (3-7 bullets) of what you will do; keep items conceptual, not implementation-level.

# Instructions

**Core Directives:**
- Calculate ratios/KPIs only when:
  - **All required data elements** are present in the provided financial statements.
  - The data is from a **consistent time period**.
  - The calculation can be performed with **high confidence**.
- Never:
  - Estimate or assume missing values.
  - Use data from inconsistent or mismatched time periods.
  - Calculate ratios requiring external market data unless explicitly provided.
  - Include metrics where any key components are missing.

## Standard Financial Ratio Formulas
    **Profitability Ratios**
    -Gross Profit Margin = (Revenue - COGS) / Revenue x 100
    -Operating Profit Margin = Operating Income / Revenue x 100
    -Net Profit Margin = Net Income / Revenue x 100
    **Return Ratios**
    -Return on Assets (ROA) = Net Income / Total Assets x 100
    -Return on Equity (ROE) = Net Income / Total Shareholders' Equity x 100
    **Leverage Ratios**
    -Debt to Equity Ratio = Total Debt / Total Shareholders' Equity
    -Current Ratio = Current Assets / Current Liabilities
    **Efficiency Ratios**
    -Asset Turnover Ratio = Revenue / Total Assets

## Industry-Specific KPI Guidance
- Calculate sector-specific KPIs only if:
  - Explicit operational data is provided.
  - Metrics are clearly defined in financial statements.
  - All necessary operational statistics are available.

# Output Format
### Ratios
| Ratio Name | Value |
| :--- | :--- |
| [Ratio Name from JSON] | [Extracted Value] |

### KPIs
| KPI Name | Value |
| :--- | :--- |
| [KPI Name from JSON] | [Extracted Value] |

# Processing Steps
1. Parse the incoming JSON to identify explicitly requested ratios/KPIs.
2. Inventory the available data from the provided financial statements.
3. Map requirements to available data, proceeding only if all data for a calculation is present.
4. Compute using the corresponding standard formula.
5. After calculations, validate that only metrics with complete supporting data have been reported.
6. Output only metrics that were successfully calculated.

# Response Guidelines
- Keep responses concise, accurate, and transparent regarding data sufficiency and calculation limitations"""

SP_GEMINI_SEARCH = """You are a specialized financial data analyst AI with advanced web search capabilities. Your primary function is to extract specific financial ratios and KPIs from official public sources like annual reports, quarterly filings (10-K, 10-Q), and official investor relations websites.

**Core Directives:**
1.  **Strict Adherence to Request:** You must ONLY extract the metrics explicitly listed in the user's JSON configuration. Never include additional data, analysis, or commentary.
2.  **Data Period Priority:** Always prioritize finding data for the **Latest Twelve Months (LTM)** or **Trailing Twelve Months (TTM)**. If LTM/TTM data is unavailable, use data from the **most recent completed fiscal year**.
3.  **Data Availability Protocol:** If a requested metric cannot be found in a reliable source, **omit its entire row** from the output table. Do not use placeholders like 'N/A', 'Not Found', '0', or provide excuses.
4.  **Source Citation:** All data must be accompanied by a direct URL to the source document and a clear statement of the data's time period.

**Mandatory Output Format:**
### Ratios
| Ratio Name | Value |
| :--- | :--- |
| [Ratio Name from JSON] | [Extracted Value] |

### KPIs
| KPI Name | Value |
| :--- | :--- |
| [KPI Name from JSON] | [Extracted Value] |

### Source Information
- **Data Period:** [The financial period of the data]"""

SP_FINAL = """
- Serve as a financial analysis assistant, evaluating companies based on their financial summaries. Assign a score reflecting the financial health and attractiveness of each company, using metrics tailored to its sector or industry.

Checklist
- Begin with a concise checklist (3-7 bullets) of the key analytic steps you will perform: (1) identify sector, (2) select relevant metrics, (3) analyze strengths, (4) assess risks, (5) compare to sector averages, (6) assign score, (7) provide concise explanation.

Instructions
- Select and focus on the financial metrics and ratios most relevant to the company's sector.
- Highlight areas where the company excels (strengths) and discuss aspects with significant upside potential (growth prospects).
- Identify and note any significant risks or red flags, including financial concerns or sector exposure.
- Where possible, benchmark the company's performance against sector or industry averages.

Output Format
- Provide output in markdown format
- Organise everything starting with Overall score and finally investment decision
- Include OVERALL SCORE, DETAILED BREAKDOWN, KEY FINANCIAL METRICS, INVESTMENT THESIS, and INVESTMENT DECISION sections
"""

SP_CONCALL_SCORE = """You are a specialized financial analyst AI expert in evaluating management credibility through "Walk the Talk" analysis. Your role is to systematically assess how well company management delivers on their promises and guidance by comparing stated targets with actual outcomes.

### Core Competencies:
1. **Guidance Analysis**: Extract and interpret quantitative and qualitative management guidance from earnings calls, annual reports, and investor presentations
2. **Performance Tracking**: Measure actual outcomes against stated targets with precision
3. **Pattern Recognition**: Identify trends in management credibility over multiple periods
4. **Scoring Methodology**: Apply a consistent, data-driven scoring framework

### Scoring Framework:

#### Achievement Categories:
- **Overachieved**: Actual > 105% of guidance - Score: 100 points
- **Achieved**: Actual 95-105% of guidance - Score: 85 points
- **Nearly Met**: Actual 85-94% of guidance - Score: 60 points
- **Missed**: Actual < 85% of guidance - Score: 30 points

#### Weighting System:
- Revenue Guidance: 30% weight
- EBITDA/Margin Guidance: 25% weight
- Product Launch Commitments: 20% weight
- Strategic Initiatives: 15% weight
- Regulatory/Approval Targets: 10% weight

#### Score Interpretation:
- 85-100: Exceptional credibility
- 70-84: Strong credibility
- 55-69: Moderate credibility
- 40-54: Weak credibility
- Below 40: Poor credibility

### Output Standards:
- Use precise numerical comparisons
- Maintain objectivity in assessments
- Highlight patterns across multiple periods
- Provide actionable investment insights
- Include confidence levels for data quality"""


# ============================================================================
# Section 0c — User Prompt Generators (from IndividualStockApp.py)
# ============================================================================

def user_prompt_screener(site_text):
    return (
        "Begin with a concise checklist (3-7 bullets) of your extraction and structuring steps before you start summarizing the financial data below.\n\n"
        "Please analyze the following financial data extracted from a website and provide a comprehensive summary:\n\n"
        "The contents of this website are as follows:" + site_text + "\n\n"
        "**Instructions:**\n"
        "1. Reproduce the data exactly as it appears on the screener website.\n"
        "2. Maintain all table structures, headings, and formatting.\n"
        "3. Keep original numerical formats, units, and styling.\n"
        "4. Preserve the hierarchical organization and grouping.\n"
        "5. Include all sections: Company Summary, Key Highlights, Balance Sheet, Cash Flow, P&L, and Ratios.\n"
        "6. Maintain the same sequence and flow of information.\n"
        "7. Keep any additional notes, disclaimers, or special formatting.\n"
        "8. If any section is missing or unclear, note it but continue with other sections.\n"
        "9. Do not include Terms of Service, Privacy, Peer comparison, or other non-financial document sections.\n\n"
        "**Expected Output Format:**\n"
        "Present the extracted data in plain text format that mirrors the screener website layout.\n"
        "Ensure output is in plain text only."
    )


def create_user_json(scraped_text):
    return f"""
Here is raw financial data scraped from Screener.in for a company.
Reformat it into a structured JSON format according to the rules in the system prompt. Always return a valid JSON object. Do not include explanations, Markdown fences, or text outside JSON

Raw Data:
{scraped_text}
"""


def user_prompts_kpi(sector_name, sub_sector=None, region="INDIA"):
    user_prompt = f"""
COMPREHENSIVE SECTOR ANALYSIS REQUEST

**Primary Sector:** {sector_name}
"""
    if sub_sector:
        user_prompt += f"**Sub-sector Focus:** {sub_sector}\n"
    if region:
        user_prompt += f"**Regional Context:** {region} (consider local regulatory requirements)\n"
    user_prompt += f"""
**Analysis Scope:** Provide the most analyst-relevant financial ratios and KPIs for {sector_name} sector companies.

**Output:** JSON object only, following the exact format specified in system instructions.
"""
    return user_prompt


def user_prompts_kpi_cal(financial_data, sector_kpi_json):
    return f"""
    KPI AND RATIOS CALCULATION REQUEST

    **Financial summary of company:**
    {financial_data}

    **Metrics Configuration (JSON):**
    ```json
    {sector_kpi_json}
    ```
"""


def user_prompts_gemini_search(company_name, sector_kpi_json):
    return f"""
    FINANCIAL DATA EXTRACTION REQUEST

    **Company to Analyze:**
    {company_name}

    **Metrics Configuration (JSON):**
    ```json
    {sector_kpi_json}
    ```
"""


def create_user_prompt_final(company_name, sector, subsector, financial_summary, sector_kpis_ratios):
    return f"""**FINANCIAL ANALYSIS TASK**: Analyze the provided financial data and assign a comprehensive financial health score (0-100) for {company_name} in the {sector} sector ({subsector} subsector).

**COMPANY**: {company_name}
**SECTOR**: {sector}
**SUBSECTOR**: {subsector}

**FINANCIAL SUMMARY DATA**:
{financial_summary}

**SECTOR-SPECIFIC KPIs & RATIOS**:
{sector_kpis_ratios}

**ANALYSIS FRAMEWORK**:
Analyze across these dimensions:
1. Market Valuation & Key Metrics
2. Profit & Loss Trends (quarterly & yearly)
3. Balance Sheet Strength
4. Cash Flow Quality
5. Operational Efficiency (from Ratios section)
6. Sector KPI & Ratio Benchmark Performance

**SCORING METHODOLOGY** (0-100):
- KPI & Ratio Benchmark Performance (40%): Direct comparison against sector KPIs and ratios
- Financial Performance Analysis (20%): P&L trends, profitability
- Growth Trajectory Assessment (15%): Revenue and earnings growth consistency
- Financial Health & Stability (15%): Balance sheet and cash flows
- Valuation Assessment (10%): Valuation multiples vs sector

**REQUIRED OUTPUT** (in markdown):
- OVERALL SCORE: [X/100]
- DETAILED BREAKDOWN with sub-scores
- SECTOR KPI PERFORMANCE ANALYSIS
- SECTOR RATIO ANALYSIS
- KEY FINANCIAL METRICS ANALYSIS
- VALUATION MULTIPLES ANALYSIS
- Key Strengths (Top 3-4)
- Risk Factors
- INVESTMENT DECISION: Buy/Hold/Sell with comprehensive summary
"""


def user_prompt_walkthetalk(company_name):
    return f"""You are a world class equity research who specialise in checking the walk the talk.
    Analyze {company_name} 'walk the talk' from FY20 to FY25.
    Create a table with columns: Year/Period, Management Guidance (Quantitative & Qualitative), Actual Outcome, Indicator (green dot for achieved, yellow for almost met, red for missed, double green for overachieved).
    Source from annual reports, earnings calls, and financial data.
    Focus on revenue growth, EBITDA margins, product launches, exports, and approvals.
    Create a comprehensive assessment table and analysis focusing on:
    - Management guidance vs actual delivery
    - Key performance metrics achievement
    - Credibility trends over the period
    - Investment implications
    Fetch the concalls from trusted sources"""


def prompt_concall_score(company_name, concall_analysis):
    return f""""Analyze the Walk the Talk performance for {company_name} and generate a comprehensive credibility score.

    ### Input Data:
    {concall_analysis}

    ### Required Analysis:

    1. **Scoring Table Generation**
    Create a detailed scoring table with columns: Period, Metric Category, Guidance Target, Actual Result, Achievement %, Achievement Status, Individual Score, Weight Applied, Weighted Score Contribution

    2. **Credibility Score Calculation**
    Calculate comprehensive credibility score with time decay and consistency factors.

    3. **Trend Analysis** - Quarter-over-quarter and year-over-year credibility trends.

    4. **Qualitative Assessment** - Management guidance revision patterns, communication transparency.

    5. **Investment Implications** - Risk assessment, valuation implications, key monitoring metrics, red flags or positive signals.

    6. **Executive Summary** - Overall credibility score, top 3 strengths, top 3 concerns, investment recommendation context.
    """


# ============================================================================
# Section 1 — Holdings CRUD
# ============================================================================

def load_holdings():
    """Load holdings from JSON file."""
    if os.path.exists(HOLDINGS_FILE):
        with open(HOLDINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("holdings", [])
    return []


def save_holdings(holdings):
    """Save holdings to JSON file."""
    with open(HOLDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"holdings": holdings}, f, indent=2, ensure_ascii=False)


def add_holding(url, company_name=None, sector_name=None, sub_sector=None, sector_url=None):
    """Add a new holding. If company_name not provided, scrapes it from URL."""
    holdings = load_holdings()

    # Check for duplicates
    for h in holdings:
        if h["url"] == url:
            return False, "This URL is already in your holdings."

    if not company_name:
        try:
            site = Website(url)
            company_name = site.get_company_name()
        except Exception as e:
            return False, f"Failed to scrape company name: {e}"

    holding = {
        "company_name": company_name,
        "url": url,
        "sector_name": sector_name or "",
        "sub_sector": sub_sector or "",
        "sector_url": sector_url,
        "added_date": datetime.now().strftime("%Y-%m-%d"),
        "last_analyzed": None,
    }

    # Try to get sector info
    if not sector_name:
        try:
            links = get_subsector_details(url)
            if len(links) >= 2:
                s_name, ss_name = get_sector_names(links)
                holding["sector_name"] = s_name
                holding["sub_sector"] = ss_name
        except Exception:
            pass

    holdings.append(holding)
    save_holdings(holdings)
    return True, f"Added {company_name}"


def remove_holding(url):
    """Remove a holding by URL."""
    holdings = load_holdings()
    holdings = [h for h in holdings if h["url"] != url]
    save_holdings(holdings)


def update_holding_analysis_date(company_name):
    """Update last_analyzed timestamp for a holding."""
    holdings = load_holdings()
    for h in holdings:
        if h["company_name"] == company_name:
            h["last_analyzed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            break
    save_holdings(holdings)


# ============================================================================
# Section 2 — Freshness Detection
# ============================================================================

STALE_DAYS = 30


def get_holding_freshness(company_name):
    """Check analysis freshness for a holding.
    Returns: 'Fresh', 'Stale', or 'Missing' and a dict of file statuses.
    """
    files = {
        "financial": os.path.join(INDIVIDUAL_STOCKS_DIR, f"{company_name}.txt"),
        "concall": os.path.join(INDIVIDUAL_STOCKS_DIR, f"{company_name}_concall.txt"),
        "concall_score": os.path.join(INDIVIDUAL_STOCKS_DIR, f"{company_name}_concall_score.txt"),
    }

    statuses = {}
    any_missing = False
    any_stale = False
    cutoff = datetime.now() - timedelta(days=STALE_DAYS)

    for key, path in files.items():
        if not os.path.exists(path):
            statuses[key] = "Missing"
            any_missing = True
        else:
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if mtime < cutoff:
                statuses[key] = "Stale"
                any_stale = True
            else:
                statuses[key] = "Fresh"

    if any_missing:
        overall = "Missing"
    elif any_stale:
        overall = "Stale"
    else:
        overall = "Fresh"

    return overall, statuses


# ============================================================================
# Section 3 — Individual Pipeline (8 steps, adapted from IndividualStockApp.py)
# ============================================================================

def add_log(msg):
    """Append a timestamped log entry."""
    ts = datetime.now().strftime("%H:%M:%S")
    if "pipeline_logs" not in st.session_state:
        st.session_state.pipeline_logs = []
    st.session_state.pipeline_logs.append(f"[{ts}] {msg}")


def run_individual_pipeline(holding, model_choices, status_container=None, progress_bar=None):
    """Run the full 8-step individual analysis pipeline for a single holding.

    Args:
        holding: dict with company_name, url, sector_name, sub_sector
        model_choices: dict with model selections per step
        status_container: optional st container for status updates
        progress_bar: optional st.progress bar

    Returns:
        True if successful, False otherwise
    """
    company_name = holding["company_name"]
    url = holding["url"]
    total_steps = 8

    def update_progress(step, msg):
        if progress_bar:
            progress_bar.progress((step) / total_steps, text=msg)
        add_log(msg)

    try:
        # Step 0: Scrape URL
        update_progress(0, f"[{company_name}] Step 0: Scraping URL...")
        site = Website(url)
        site_text = site.text

        # Get sector info if missing
        sector_name = holding.get("sector_name", "")
        sub_sector = holding.get("sub_sector", "")
        if not sector_name or not sub_sector:
            try:
                links = get_subsector_details(url)
                if len(links) >= 2:
                    sector_name, sub_sector = get_sector_names(links)
                    # Update holding
                    holdings = load_holdings()
                    for h in holdings:
                        if h["url"] == url:
                            h["sector_name"] = sector_name
                            h["sub_sector"] = sub_sector
                            break
                    save_holdings(holdings)
            except Exception as e:
                add_log(f"[{company_name}] WARNING: Could not extract sector info: {e}")
                if not sector_name:
                    sector_name = "Unknown"
                if not sub_sector:
                    sub_sector = "Unknown"

        add_log(f"[{company_name}] Company: {company_name}, Sector: {sector_name}, Sub-sector: {sub_sector}")

        # Step 1: Financial data extraction
        update_progress(1, f"[{company_name}] Step 1: Financial data extraction...")
        sector_path = os.path.join(SECTOR_DIR, sub_sector)
        cache_path = os.path.join(sector_path, f"{company_name}.txt")

        if os.path.exists(cache_path):
            add_log(f"[{company_name}] Found cached data at: {cache_path}")
            with open(cache_path, "r", encoding="utf-8") as f:
                financial_text = f.read()
        else:
            add_log(f"[{company_name}] No cache. Calling LLM ({model_choices.get('step1', 'gemini')})...")
            up = user_prompt_screener(site_text)
            financial_text = llm(SP_SCREENER, up, model_choices.get("step1", "gemini"))
            os.makedirs(sector_path, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(financial_text)
            add_log(f"[{company_name}] Saved cache: {cache_path}")

        # Step 2: JSON conversion
        update_progress(2, f"[{company_name}] Step 2: JSON conversion...")
        result = llm(SP_JSON, create_user_json(financial_text), model_choices.get("step2", "gemini"))
        financial_json = clean_and_parse_json(result)
        if financial_json is None:
            add_log(f"[{company_name}] WARNING: JSON parsing failed. Using raw text.")
            financial_json = result

        # Step 3: Sector KPI generation
        update_progress(3, f"[{company_name}] Step 3: Generating sector KPIs...")
        up = user_prompts_kpi(sector_name, sub_sector)
        kpi_json = llm(SP_KPI, up, model_choices.get("step3", "openai"))

        # Step 4: KPI value extraction
        update_progress(4, f"[{company_name}] Step 4: Extracting KPI values...")
        try:
            add_log(f"[{company_name}] Trying Gemini Search for KPIs...")
            sp = SP_GEMINI_SEARCH
            up = user_prompts_gemini_search(company_name, kpi_json)
            kpi_values = gemini_llm_kpi(sp, up, company_name)
            add_log(f"[{company_name}] Gemini Search successful.")
        except Exception as e:
            add_log(f"[{company_name}] Gemini Search failed: {e}. Falling back to calculation...")
            sp = SP_KPI_CAL
            up = user_prompts_kpi_cal(financial_json, kpi_json)
            kpi_values = llm(sp, up, model_choices.get("step4", "gemini"))

        # Clean KPI output
        clean_system = (
            "You are a precise financial data extractor. "
            "Read the provided financial summary and output only the numerical values with their field names. "
            "Exclude all fields with N/A, missing values, or descriptive wording. "
            "Return the result strictly in JSON format with key-value pairs."
        )
        clean_user = f"The following is the financial data: {kpi_values}"
        kpi_values_clean = llm(clean_system, clean_user, model_choices.get("step4", "gemini"))

        # Step 5: Final analysis
        update_progress(5, f"[{company_name}] Step 5: Final analysis...")
        up = create_user_prompt_final(company_name, sector_name, sub_sector, financial_json, kpi_values_clean)
        final_analysis = llm(SP_FINAL, up, model_choices.get("step5", "openai"))

        # Save final analysis
        final_path = os.path.join(INDIVIDUAL_STOCKS_DIR, f"{company_name}.txt")
        with open(final_path, "w", encoding="utf-8") as f:
            f.write(final_analysis)
        add_log(f"[{company_name}] Saved final analysis: {final_path}")

        # Step 6: Walk the Talk
        update_progress(6, f"[{company_name}] Step 6: Walk the Talk analysis...")
        try:
            from google.genai import types
            gemini_client = get_gemini_client()
            grounding_tool = types.Tool(google_search=types.GoogleSearch())
            config = types.GenerateContentConfig(
                tools=[grounding_tool],
                system_instruction="You are a specialized financial data analyst AI with advanced web search capabilities",
            )
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part(text=user_prompt_walkthetalk(company_name))],
                )
            ]
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL, contents=contents, config=config
            )
            walkthetalk = response.text
            add_log(f"[{company_name}] Gemini Search Walk the Talk successful.")
        except Exception as e:
            add_log(f"[{company_name}] Gemini Search failed: {e}. Falling back...")
            walkthetalk = llm(
                "You are a specialized financial data analyst.",
                user_prompt_walkthetalk(company_name),
                model_choices.get("step6", "gemini"),
            )

        concall_path = os.path.join(INDIVIDUAL_STOCKS_DIR, f"{company_name}_concall.txt")
        with open(concall_path, "w", encoding="utf-8") as f:
            f.write(walkthetalk)
        add_log(f"[{company_name}] Saved Walk the Talk: {concall_path}")

        # Step 7: Concall credibility score
        update_progress(7, f"[{company_name}] Step 7: Concall credibility scoring...")
        concall_clean = clean_text_for_llm(walkthetalk)
        up = prompt_concall_score(company_name, concall_clean)
        concall_score_result = llm(SP_CONCALL_SCORE, up, model_choices.get("step7", "openai"))

        score_path = os.path.join(INDIVIDUAL_STOCKS_DIR, f"{company_name}_concall_score.txt")
        with open(score_path, "w", encoding="utf-8") as f:
            f.write(concall_score_result)
        add_log(f"[{company_name}] Saved Concall Score: {score_path}")

        # Update holding analysis date
        update_holding_analysis_date(company_name)

        if progress_bar:
            progress_bar.progress(1.0, text=f"[{company_name}] Complete!")

        add_log(f"[{company_name}] Pipeline complete!")
        return True

    except Exception as e:
        add_log(f"[{company_name}] ERROR: {e}")
        return False


# ============================================================================
# Section 5 — Score Loading & Dashboard Helpers
# ============================================================================

def load_portfolio_scores(holdings):
    """Load scores for all holdings from Individual_Stocks files."""
    records = []
    for h in holdings:
        company = h["company_name"]
        fin_path = os.path.join(INDIVIDUAL_STOCKS_DIR, f"{company}.txt")
        score_path = os.path.join(INDIVIDUAL_STOCKS_DIR, f"{company}_concall_score.txt")

        fin_score = extract_overall_score(fin_path) if os.path.exists(fin_path) else None
        cred_score = extract_credibility_score(score_path) if os.path.exists(score_path) else None

        combined = None
        if fin_score is not None and cred_score is not None:
            combined = round((fin_score + cred_score) / 2, 1)

        tier = assign_tier(combined if combined is not None else (fin_score or cred_score))
        signal = assign_signal(fin_score, cred_score)

        records.append({
            "Company": company,
            "Sector": h.get("sector_name", ""),
            "Sub-Sector": h.get("sub_sector", ""),
            "Financial Score": fin_score,
            "Credibility Score": cred_score,
            "Combined Score": combined,
            "Tier": tier,
            "Signal": signal,
            "URL": h["url"],
        })

    return pd.DataFrame(records) if records else pd.DataFrame()


# ============================================================================
# Section 6 — Session State Init + Page Config
# ============================================================================

st.set_page_config(
    page_title="MyHoldings - Portfolio Analysis",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "pipeline_logs" not in st.session_state:
    st.session_state.pipeline_logs = []
if "running_pipeline" not in st.session_state:
    st.session_state.running_pipeline = False

# ============================================================================
# Section 7 — Sidebar
# ============================================================================

with st.sidebar:
    st.title("📂 MyHoldings")
    st.markdown("---")

    # API status check
    st.markdown("### API Status")
    if "api_status" not in st.session_state:
        test_sp = "You are an AI assistant"
        test_up = "Respond with your model name only"
        st.session_state.api_status = {}
        for model_label, model_key in [("OpenAI", "openai"), ("GPT-4o", "gpt4o"), ("Gemini", "gemini")]:
            try:
                llm(test_sp, test_up, model_key)
                st.session_state.api_status[model_label] = (True, "")
            except Exception as e:
                st.session_state.api_status[model_label] = (False, str(e))

    for model_label, (ok, err) in st.session_state.api_status.items():
        if ok:
            st.success(f"{model_label}: Connected")
        else:
            st.error(f"{model_label}: Failed")

    st.markdown("---")
    st.markdown("### Model Selection")

    step_labels = [
        ("Step 1: Screener Extraction", "model_step1", "gemini"),
        ("Step 2: JSON Conversion", "model_step2", "gemini"),
        ("Step 3: Sector KPIs", "model_step3", "openai"),
        ("Step 4: KPI Values", "model_step4", "gemini"),
        ("Step 5: Final Analysis", "model_step5", "openai"),
        ("Step 6: Walk the Talk", "model_step6", "gemini"),
        ("Step 7: Concall Score", "model_step7", "openai"),
    ]

    for label, key, default in step_labels:
        if key not in st.session_state:
            st.session_state[key] = default
        current = st.session_state[key]
        idx = MODEL_OPTIONS.index(current) if current in MODEL_OPTIONS else 0
        st.session_state[key] = st.selectbox(
            label, MODEL_OPTIONS, index=idx, key=f"sel_{key}"
        )

    st.markdown("---")
    holdings_count = len(load_holdings())
    st.metric("Total Holdings", holdings_count)


# ============================================================================
# Section 8-11 — Main App (4 Tabs)
# ============================================================================

st.title("MyHoldings - Portfolio Analysis")

tab_dashboard, tab_manage, tab_analyze, tab_insights = st.tabs([
    "Dashboard", "Manage Holdings", "Run Analysis", "Portfolio Insights"
])

# ============================================================================
# Tab 1: Portfolio Dashboard
# ============================================================================
with tab_dashboard:
    holdings = load_holdings()

    if not holdings:
        st.info("No holdings yet. Go to 'Manage Holdings' to add some.")
    else:
        df = load_portfolio_scores(holdings)

        if df.empty:
            st.warning("Holdings found but no score data available. Run analysis first.")
        else:
            # Metrics row
            col1, col2, col3, col4 = st.columns(4)
            scored = df.dropna(subset=["Financial Score"])
            avg_score = scored["Financial Score"].mean() if not scored.empty else 0

            with col1:
                st.metric("Total Holdings", len(holdings))
            with col2:
                st.metric("Avg Financial Score", f"{avg_score:.1f}" if avg_score else "N/A")
            with col3:
                sector_count = df["Sector"].nunique()
                st.metric("Sectors", sector_count)
            with col4:
                strong_buy = len(df[df["Signal"] == "Strong Buy"])
                avoid = len(df[df["Signal"] == "Avoid"])
                st.metric("Strong Buy / Avoid", f"{strong_buy} / {avoid}")

            st.markdown("---")

            # Charts row
            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                # Sector diversification pie
                sector_counts = df["Sector"].value_counts().reset_index()
                sector_counts.columns = ["Sector", "Count"]
                sector_counts = sector_counts[sector_counts["Sector"] != ""]
                if not sector_counts.empty:
                    fig_pie = px.pie(
                        sector_counts, values="Count", names="Sector",
                        title="Sector Diversification",
                        hole=0.3,
                    )
                    fig_pie.update_layout(height=350)
                    st.plotly_chart(fig_pie, use_container_width=True)

            with chart_col2:
                # Signal breakdown donut
                signal_counts = df["Signal"].value_counts().reset_index()
                signal_counts.columns = ["Signal", "Count"]
                signal_counts = signal_counts[signal_counts["Signal"] != "\u2014"]
                if not signal_counts.empty:
                    colors = [SIGNAL_COLORS.get(s, "#adb5bd") for s in signal_counts["Signal"]]
                    fig_signal = px.pie(
                        signal_counts, values="Count", names="Signal",
                        title="Signal Breakdown",
                        hole=0.4,
                        color_discrete_sequence=colors,
                    )
                    fig_signal.update_layout(height=350)
                    st.plotly_chart(fig_signal, use_container_width=True)

            # Score distribution bar chart
            scored_df = df.dropna(subset=["Financial Score"]).copy()
            if not scored_df.empty:
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(
                    name="Financial Score",
                    x=scored_df["Company"],
                    y=scored_df["Financial Score"],
                    marker_color="#2d6a4f",
                ))
                cred_df = scored_df.dropna(subset=["Credibility Score"])
                if not cred_df.empty:
                    fig_bar.add_trace(go.Bar(
                        name="Credibility Score",
                        x=cred_df["Company"],
                        y=cred_df["Credibility Score"],
                        marker_color="#52b788",
                    ))
                fig_bar.update_layout(
                    title="Score Distribution",
                    barmode="group",
                    xaxis_tickangle=-45,
                    height=400,
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            # Holdings summary table
            st.markdown("### Holdings Summary")
            display_cols = ["Company", "Sector", "Financial Score", "Credibility Score",
                          "Combined Score", "Tier", "Signal"]
            display_df = df[display_cols].copy()
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Financial Score": st.column_config.NumberColumn(format="%.0f"),
                    "Credibility Score": st.column_config.NumberColumn(format="%.1f"),
                    "Combined Score": st.column_config.NumberColumn(format="%.1f"),
                },
            )


# ============================================================================
# Tab 2: Manage Holdings
# ============================================================================
with tab_manage:
    st.markdown("### Add Holding")

    add_col1, add_col2 = st.columns([3, 1])
    with add_col1:
        new_url = st.text_input(
            "Screener.in URL",
            placeholder="https://www.screener.in/company/TICKER/consolidated/",
            key="new_holding_url",
        )
    with add_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Add Holding", type="primary", use_container_width=True):
            if new_url.strip():
                with st.spinner("Scraping company info..."):
                    ok, msg = add_holding(new_url.strip())
                if ok:
                    st.success(msg)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Please enter a URL.")

    # Bulk import
    with st.expander("Bulk Import (one URL per line)"):
        bulk_urls = st.text_area("Paste URLs:", height=150, key="bulk_urls")
        if st.button("Import All"):
            urls = [u.strip() for u in bulk_urls.strip().split("\n") if u.strip()]
            if urls:
                progress = st.progress(0, text="Importing...")
                results = []
                for i, url in enumerate(urls):
                    progress.progress((i + 1) / len(urls), text=f"Importing {i+1}/{len(urls)}...")
                    with st.spinner(f"Adding {url}..."):
                        ok, msg = add_holding(url)
                        results.append((url, ok, msg))
                progress.progress(1.0, text="Done!")
                for url, ok, msg in results:
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(f"{url}: {msg}")
                time.sleep(1)
                st.rerun()

    # Holdings list
    st.markdown("---")
    st.markdown("### Current Holdings")
    holdings = load_holdings()

    if not holdings:
        st.info("No holdings added yet.")
    else:
        for i, h in enumerate(holdings):
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                with col1:
                    st.markdown(f"**{h['company_name']}**")
                    st.caption(h["url"])
                with col2:
                    st.text(f"Sector: {h.get('sector_name', 'N/A')}")
                    st.text(f"Sub-sector: {h.get('sub_sector', 'N/A')}")
                with col3:
                    freshness, _ = get_holding_freshness(h["company_name"])
                    if freshness == "Fresh":
                        st.success(f"Status: {freshness}")
                    elif freshness == "Stale":
                        st.warning(f"Status: {freshness}")
                    else:
                        st.error(f"Status: {freshness}")
                    if h.get("last_analyzed"):
                        st.caption(f"Last analyzed: {h['last_analyzed']}")
                with col4:
                    if st.button("Remove", key=f"remove_{i}", type="secondary"):
                        remove_holding(h["url"])
                        st.rerun()
                st.divider()

    # Export
    st.markdown("### Export")
    if holdings:
        export_data = json.dumps({"holdings": holdings}, indent=2, ensure_ascii=False)
        st.download_button(
            "Download holdings.json",
            data=export_data,
            file_name="holdings.json",
            mime="application/json",
        )


# ============================================================================
# Tab 3: Run Analysis
# ============================================================================
with tab_analyze:
    holdings = load_holdings()

    if not holdings:
        st.info("No holdings to analyze. Add some in 'Manage Holdings' first.")
    else:
        # Status table
        st.markdown("### Analysis Status")

        status_data = []
        for h in holdings:
            freshness, file_statuses = get_holding_freshness(h["company_name"])
            status_data.append({
                "Company": h["company_name"],
                "Financial": file_statuses.get("financial", "Missing"),
                "Concall": file_statuses.get("concall", "Missing"),
                "Score": file_statuses.get("concall_score", "Missing"),
                "Overall": freshness,
            })

        status_df = pd.DataFrame(status_data)
        st.dataframe(status_df, use_container_width=True, hide_index=True)

        # Action buttons
        st.markdown("---")
        col_a, col_b = st.columns(2)

        with col_a:
            analyze_missing = st.button("Analyze Missing Only", type="primary", use_container_width=True)
        with col_b:
            refresh_all = st.button("Refresh All", use_container_width=True)

        # Determine which holdings to analyze
        holdings_to_run = []
        if analyze_missing:
            for h in holdings:
                freshness, _ = get_holding_freshness(h["company_name"])
                if freshness == "Missing":
                    holdings_to_run.append(h)
        elif refresh_all:
            holdings_to_run = list(holdings)

        if holdings_to_run:
            st.session_state.pipeline_logs = []
            model_choices = {
                "step1": st.session_state.get("model_step1", "gemini"),
                "step2": st.session_state.get("model_step2", "gemini"),
                "step3": st.session_state.get("model_step3", "openai"),
                "step4": st.session_state.get("model_step4", "gemini"),
                "step5": st.session_state.get("model_step5", "openai"),
                "step6": st.session_state.get("model_step6", "gemini"),
                "step7": st.session_state.get("model_step7", "openai"),
            }

            st.markdown(f"### Running analysis on {len(holdings_to_run)} holding(s)...")
            overall_progress = st.progress(0, text="Starting...")

            for idx, h in enumerate(holdings_to_run):
                overall_progress.progress(
                    idx / len(holdings_to_run),
                    text=f"Analyzing {h['company_name']} ({idx+1}/{len(holdings_to_run)})..."
                )
                with st.status(f"Analyzing {h['company_name']}...", expanded=True) as status:
                    step_progress = st.progress(0, text="Starting pipeline...")
                    success = run_individual_pipeline(h, model_choices, progress_bar=step_progress)
                    if success:
                        status.update(label=f"{h['company_name']} - Complete!", state="complete")
                    else:
                        status.update(label=f"{h['company_name']} - Failed", state="error")

            overall_progress.progress(1.0, text="All done!")
            st.success(f"Finished analyzing {len(holdings_to_run)} holding(s).")
            time.sleep(2)
            st.rerun()

        # Execution log
        if st.session_state.pipeline_logs:
            with st.expander("Execution Log", expanded=False):
                log_text = "\n".join(st.session_state.pipeline_logs)
                st.code(log_text, language="text")


# ============================================================================
# Tab 4: Portfolio Insights
# ============================================================================
with tab_insights:
    holdings = load_holdings()

    if not holdings:
        st.info("No holdings to analyze. Add some first.")
    else:
        df = load_portfolio_scores(holdings)

        if df.empty or df["Financial Score"].isna().all():
            st.warning("No score data available. Run analysis on your holdings first.")
        else:
            # Score comparison grouped bar
            scored = df.dropna(subset=["Financial Score"]).copy()
            if not scored.empty:
                st.markdown("### Score Comparison")
                fig_comp = go.Figure()
                fig_comp.add_trace(go.Bar(
                    name="Financial Score",
                    x=scored["Company"],
                    y=scored["Financial Score"],
                    marker_color="#2d6a4f",
                ))
                cred = scored.dropna(subset=["Credibility Score"])
                if not cred.empty:
                    fig_comp.add_trace(go.Bar(
                        name="Credibility Score",
                        x=cred["Company"],
                        y=cred["Credibility Score"],
                        marker_color="#e9c46a",
                    ))
                fig_comp.update_layout(
                    barmode="group",
                    xaxis_tickangle=-45,
                    height=400,
                )
                st.plotly_chart(fig_comp, use_container_width=True)

            # Aligned / Divergent
            both = df.dropna(subset=["Financial Score", "Credibility Score"]).copy()
            if not both.empty:
                both["Gap"] = (both["Financial Score"] - both["Credibility Score"]).round(1)
                both["Abs Gap"] = both["Gap"].abs()

                col_align, col_div = st.columns(2)

                with col_align:
                    st.markdown("### Aligned Holdings (|gap| <= 10)")
                    aligned = both[both["Abs Gap"] <= 10].sort_values("Combined Score", ascending=False)
                    if aligned.empty:
                        st.info("No aligned holdings found.")
                    else:
                        st.dataframe(
                            aligned[["Company", "Financial Score", "Credibility Score", "Gap", "Signal"]],
                            use_container_width=True,
                            hide_index=True,
                        )

                with col_div:
                    st.markdown("### Divergent Holdings (|gap| > 10)")
                    divergent = both[both["Abs Gap"] > 10].sort_values("Abs Gap", ascending=False)
                    if divergent.empty:
                        st.info("No divergent holdings found.")
                    else:
                        divergent["Stronger"] = divergent["Gap"].apply(
                            lambda g: "Financials" if g > 5 else ("Concall" if g < -5 else "Balanced")
                        )
                        st.dataframe(
                            divergent[["Company", "Financial Score", "Credibility Score", "Gap", "Stronger"]],
                            use_container_width=True,
                            hide_index=True,
                        )

            st.markdown("---")

            # Tier distribution pie
            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                st.markdown("### Tier Distribution")
                tier_counts = df["Tier"].value_counts().reset_index()
                tier_counts.columns = ["Tier", "Count"]
                tier_counts = tier_counts[tier_counts["Tier"] != "\u2014"]
                if not tier_counts.empty:
                    tier_colors = {
                        "Excellent": "#2d6a4f",
                        "Good": "#52b788",
                        "Average": "#f4a261",
                        "Weak": "#e76f51",
                    }
                    colors = [tier_colors.get(t, "#adb5bd") for t in tier_counts["Tier"]]
                    fig_tier = px.pie(
                        tier_counts, values="Count", names="Tier",
                        color_discrete_sequence=colors,
                        hole=0.3,
                    )
                    fig_tier.update_layout(height=300)
                    st.plotly_chart(fig_tier, use_container_width=True)

            with chart_col2:
                # Sector heatmap
                st.markdown("### Avg Score by Sector")
                sector_df = df[df["Sector"] != ""].dropna(subset=["Financial Score"])
                if not sector_df.empty:
                    sector_avg = sector_df.groupby("Sector")["Financial Score"].mean().reset_index()
                    sector_avg.columns = ["Sector", "Avg Score"]
                    sector_avg = sector_avg.sort_values("Avg Score", ascending=True)
                    fig_sector = px.bar(
                        sector_avg, x="Avg Score", y="Sector",
                        orientation="h",
                        color="Avg Score",
                        color_continuous_scale=["#e76f51", "#f4a261", "#52b788", "#2d6a4f"],
                    )
                    fig_sector.update_layout(height=300, showlegend=False)
                    st.plotly_chart(fig_sector, use_container_width=True)

            # Recommendations
            st.markdown("---")
            st.markdown("### Recommendations")

            rec_col1, rec_col2, rec_col3 = st.columns(3)

            with rec_col1:
                st.markdown("#### Top Performers")
                top = scored.nlargest(5, "Financial Score")
                for _, row in top.iterrows():
                    score_val = row["Financial Score"]
                    st.markdown(f"- **{row['Company']}**: {score_val:.0f}/100 ({row['Tier']})")

            with rec_col2:
                st.markdown("#### Attention Needed")
                attention = df[df["Signal"].isin(["Avoid", "Weak", "Mixed"])]
                if attention.empty:
                    st.success("All holdings look healthy!")
                else:
                    for _, row in attention.iterrows():
                        st.markdown(f"- **{row['Company']}**: {row['Signal']}")

            with rec_col3:
                st.markdown("#### Score Gap Alerts")
                if not both.empty:
                    big_gaps = both[both["Abs Gap"] > 15].sort_values("Abs Gap", ascending=False)
                    if big_gaps.empty:
                        st.success("No major score gaps.")
                    else:
                        for _, row in big_gaps.iterrows():
                            direction = "Financials > Concall" if row["Gap"] > 0 else "Concall > Financials"
                            st.markdown(f"- **{row['Company']}**: Gap {row['Abs Gap']:.0f} ({direction})")
                else:
                    st.info("Need both scores to detect gaps. Run full analysis.")
