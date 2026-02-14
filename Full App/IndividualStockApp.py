"""
Streamlit Interactive Stock Analysis App
Ports the Individual_stock_analysis.ipynb pipeline into an interactive web app.
"""

# ============================================================================
# Section 0 - Imports & Config
# ============================================================================
import streamlit as st
import os
import re
import json
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

st.set_page_config(
    page_title="Stock Analysis Pipeline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Model constants
OPENAI_MODEL = "gpt-4.1-mini-2025-04-14"
GPT4O = "gpt-4o-mini-2024-07-18"
GEMINI_MODEL = "gemini-3-pro-preview"

# Base paths derived from this file's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SECTOR_DIR = os.path.join(PROJECT_ROOT, "Sector")
INDIVIDUAL_STOCKS_DIR = os.path.join(PROJECT_ROOT, "Individual_Stocks")
os.makedirs(INDIVIDUAL_STOCKS_DIR, exist_ok=True)

MODEL_OPTIONS = ["gemini", "openai", "gpt4o"]


@st.cache_resource
def get_openai_client():
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


@st.cache_resource
def get_gemini_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    from google import genai

    return genai.Client(api_key=api_key)


# ============================================================================
# Section 1 - Utility Functions
# ============================================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
}


class Website:
    """Utility class to represent a scraped webpage."""

    def __init__(self, url):
        self.url = url
        response = requests.get(self.url, headers=HEADERS)
        self.body = response.content
        soup = BeautifulSoup(self.body, "html.parser")
        self.title = soup.title.string if soup.title else "No title found"
        if soup.body:
            for irrelevant in soup.body(["script", "style", "img", "input"]):
                irrelevant.decompose()
            self.text = soup.body.get_text(separator="\n", strip=True)
        else:
            self.text = ""
        links = [link.get("href") for link in soup.find_all("a")]
        self.links = [link for link in links if link]

    def get_title(self):
        # BUG FIX: was referencing global `site`, now uses `self`
        match = re.search(r"\n\s*(.*?)\n\s*- Screener", self.title)
        if match:
            return match.group(1).strip()
        return self.title

    def get_company_name(self):
        return self.title.split(" share price")[0]


def add_log(msg):
    """Append a timestamped log entry to session state."""
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{ts}] {msg}")


def build_prompt(system_prompt, user_prompt, model_name):
    if model_name == "gemini":
        return f"{system_prompt}\n\n{user_prompt}"
    elif model_name in ("openai", "gpt4o"):
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    else:
        return None


def llm(system_prompt, user_prompt, model_name):
    match model_name:
        case "gemini":
            gemini_client = get_gemini_client()
            if gemini_client is None:
                raise ValueError("GOOGLE_API_KEY is not set. Cannot use Gemini model.")
            prompts = build_prompt(system_prompt, user_prompt, "gemini")
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompts}]}],
            )
            return response.candidates[0].content.parts[0].text
        case "openai":
            openai_client = get_openai_client()
            if openai_client is None:
                raise ValueError("OPENAI_API_KEY is not set. Cannot use OpenAI model.")
            prompts = build_prompt(system_prompt, user_prompt, "openai")
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL, messages=prompts
            )
            return response.choices[0].message.content
        case "gpt4o":
            openai_client = get_openai_client()
            if openai_client is None:
                raise ValueError("OPENAI_API_KEY is not set. Cannot use GPT-4o model.")
            prompts = build_prompt(system_prompt, user_prompt, "openai")
            response = openai_client.chat.completions.create(
                model=GPT4O, messages=prompts
            )
            return response.choices[0].message.content
        case _:
            return "Unknown model"


def get_subsector_details(url):
    screener_links = []
    site = Website(url)
    for link in site.links:
        if link.startswith("/market/"):
            screener_links.append("https://www.screener.in" + link)
    return screener_links


def get_sector_names(company_links):
    if len(company_links) < 2:
        raise ValueError(f"Expected at least 2 market links, got {len(company_links)}")
    # Only fetch the last two links (sector and sub-sector)
    sector_titles = []
    for link in company_links[-2:]:
        site = Website(link)
        time.sleep(1)
        title = site.title.strip().split("\n")[0].strip()
        sector_titles.append(title)
    return sector_titles[0], sector_titles[1]


def clean_and_parse_json(llm_output):
    cleaned = llm_output.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip().strip("'").strip('"')
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        add_log(f"JSON parsing error: {e}")
        return None


def gemini_llm_kpi(system_prompt, user_prompt, company_name):
    from google.genai import types

    gemini_client = get_gemini_client()
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[grounding_tool], system_instruction=system_prompt
    )
    contents = [
        types.Content(role="user", parts=[types.Part(text=user_prompt)])
    ]
    response = gemini_client.models.generate_content(
        model="gemini-3-pro-preview", contents=contents, config=config
    )
    return response.text


def clean_text_for_llm(text):
    text = re.sub(r"\[cite:.*?\]", "", text)
    text = re.sub(r"[🔴🟢🟡🔵⚪⚫🟠🟣🟤✅❌⭐]", "", text)
    text = re.sub(r"\n\s*:[-:|\s]+\n", "\n", text)
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        if "|" in line:
            cells = line.split("|")
            if any(len(cell.strip()) > 500 for cell in cells):
                continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"#{4,}", "###", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()


# ============================================================================
# Section 2 - Default Prompts
# ============================================================================

DEFAULT_SYSTEM_PROMPT_SCREENER = """
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

DEFAULT_SYSTEM_PROMPT_JSON = """
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

DEFAULT_SYSTEM_PROMPT_KPI = """
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

DEFAULT_SYSTEM_PROMPT_KPI_CAL = """Developer: # Role and Objective
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

DEFAULT_SYSTEM_PROMPT_GEMINI_SEARCH = """You are a specialized financial data analyst AI with advanced web search capabilities. Your primary function is to extract specific financial ratios and KPIs from official public sources like annual reports, quarterly filings (10-K, 10-Q), and official investor relations websites.

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

DEFAULT_SYSTEM_PROMPT_FINAL = """
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

DEFAULT_SYSTEM_PROMPT_CONCALL_SCORE = """You are a specialized financial analyst AI expert in evaluating management credibility through "Walk the Talk" analysis. Your role is to systematically assess how well company management delivers on their promises and guidance by comparing stated targets with actual outcomes.

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


# -- User prompt generator functions --


def user_prompt_screener(site_text):
    """Generate user prompt for screener data extraction. Uses pre-scraped text."""
    user_prompt = (
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
    return user_prompt


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


def create_user_prompt_final(
    company_name, sector, subsector, financial_summary, sector_kpis_ratios
):
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
# Section 3 - Session State Init
# ============================================================================

DEFAULTS = {
    "url": "",
    "company_name": "",
    "sector_name": "",
    "sub_sector": "",
    "site_text": "",
    # Model choices per step
    "model_step1": "gemini",
    "model_step2": "gemini",
    "model_step3": "openai",
    "model_step4": "gemini",  # Gemini search
    "model_step5": "openai",
    "model_step6": "gemini",  # Walk the talk (Gemini search)
    "model_step7": "openai",
    # Editable system prompts
    "sp_screener": DEFAULT_SYSTEM_PROMPT_SCREENER,
    "sp_json": DEFAULT_SYSTEM_PROMPT_JSON,
    "sp_kpi": DEFAULT_SYSTEM_PROMPT_KPI,
    "sp_kpi_cal": DEFAULT_SYSTEM_PROMPT_KPI_CAL,
    "sp_gemini_search": DEFAULT_SYSTEM_PROMPT_GEMINI_SEARCH,
    "sp_final": DEFAULT_SYSTEM_PROMPT_FINAL,
    "sp_concall_score": DEFAULT_SYSTEM_PROMPT_CONCALL_SCORE,
    # Step results
    "result_scrape": None,
    "result_financial_text": None,
    "result_financial_json": None,
    "result_kpi_json": None,
    "result_kpi_values": None,
    "result_kpi_values_clean": None,
    "result_final_analysis": None,
    "result_walkthetalk": None,
    "result_concall_score": None,
    # Logs
    "logs": [],
    # Pipeline state
    "running": False,
    "current_step": -1,
    "step_by_step": False,
    "run_step": -1,
}

for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ============================================================================
# Section 4 - Sidebar
# ============================================================================

with st.sidebar:
    st.title("📊 Stock Analysis")
    st.markdown("---")

    st.session_state.url = st.text_input(
        "Screener.in URL",
        value=st.session_state.url,
        placeholder="https://www.screener.in/company/MAHABANK/consolidated/",
    )

    # API status via live test calls (cached per session)
    st.markdown("### API Status")
    if "api_status" not in st.session_state:
        test_sp = "You are an AI assistant"
        test_up = "Im testing an api call respond with your model name and latest knowledge cut off date"
        st.session_state.api_status = {}
        for model_label, model_key in [("OpenAI", "openai"), ("GPT-4o", "gpt4o"), ("Gemini", "gemini")]:
            try:
                llm(test_sp, test_up, model_key)
                st.session_state.api_status[model_label] = (True, "")
            except Exception as e:
                st.session_state.api_status[model_label] = (False, str(e))
                add_log(f"API Status Check FAILED for {model_label}: {e}")

    for model_label, (ok, err) in st.session_state.api_status.items():
        if ok:
            st.success(f"{model_label}: Connected")
        else:
            st.error(f"{model_label}: Failed — {err}")

    st.markdown("---")
    st.markdown("### Model Selection")

    step_labels = [
        ("Step 1: Screener Extraction", "model_step1"),
        ("Step 2: JSON Conversion", "model_step2"),
        ("Step 3: Sector KPIs", "model_step3"),
        ("Step 4: KPI Values (Gemini Search)", "model_step4"),
        ("Step 5: Final Analysis", "model_step5"),
        ("Step 6: Walk the Talk (Gemini Search)", "model_step6"),
        ("Step 7: Concall Score", "model_step7"),
    ]

    for label, key in step_labels:
        current = st.session_state[key]
        idx = MODEL_OPTIONS.index(current) if current in MODEL_OPTIONS else 0
        st.session_state[key] = st.selectbox(
            label, MODEL_OPTIONS, index=idx, key=f"sel_{key}"
        )

    st.markdown("---")
    st.session_state.step_by_step = st.toggle(
        "Step-by-step mode", value=st.session_state.step_by_step
    )

    col_run, col_reset = st.columns(2)
    with col_run:
        run_clicked = st.button(
            "🚀 Run Full Analysis", use_container_width=True, type="primary"
        )
    with col_reset:
        reset_clicked = st.button("🔄 Reset", use_container_width=True)

    if reset_clicked:
        for key, val in DEFAULTS.items():
            st.session_state[key] = val
        st.rerun()

# ============================================================================
# Section 5 - Prompt Editors
# ============================================================================

st.title("Stock Analysis Pipeline")

if st.session_state.company_name:
    c1, c2, c3 = st.columns(3)
    c1.metric("Company", st.session_state.company_name)
    c2.metric("Sector", st.session_state.sector_name)
    c3.metric("Sub-Sector", st.session_state.sub_sector)

with st.expander("📝 Edit System Prompts", expanded=False):
    prompt_tabs = st.tabs(
        [
            "1. Screener",
            "2. JSON",
            "3. KPI",
            "4. KPI Calc",
            "5. Gemini Search",
            "6. Final Analysis",
            "7. Concall Score",
        ]
    )
    prompt_keys = [
        "sp_screener",
        "sp_json",
        "sp_kpi",
        "sp_kpi_cal",
        "sp_gemini_search",
        "sp_final",
        "sp_concall_score",
    ]
    prompt_defaults = [
        DEFAULT_SYSTEM_PROMPT_SCREENER,
        DEFAULT_SYSTEM_PROMPT_JSON,
        DEFAULT_SYSTEM_PROMPT_KPI,
        DEFAULT_SYSTEM_PROMPT_KPI_CAL,
        DEFAULT_SYSTEM_PROMPT_GEMINI_SEARCH,
        DEFAULT_SYSTEM_PROMPT_FINAL,
        DEFAULT_SYSTEM_PROMPT_CONCALL_SCORE,
    ]
    for tab, key, default in zip(prompt_tabs, prompt_keys, prompt_defaults):
        with tab:
            st.session_state[key] = st.text_area(
                f"System Prompt ({key})",
                value=st.session_state[key],
                height=300,
                key=f"ta_{key}",
            )
    if st.button("Reset Prompts to Defaults"):
        for key, default in zip(prompt_keys, prompt_defaults):
            st.session_state[key] = default
        st.rerun()


# ============================================================================
# Section 6 - Pipeline Execution
# ============================================================================


def run_step_0():
    """Step 0: Scrape URL, extract company name/sector/sub-sector."""
    add_log("Step 0: Scraping URL...")
    url = st.session_state.url.strip()
    if not url:
        add_log("ERROR: No URL provided.")
        return False

    site = Website(url)
    st.session_state.site_text = site.text
    st.session_state.company_name = site.get_company_name()
    add_log(f"Company: {st.session_state.company_name}")

    add_log("Extracting sector and sub-sector from Screener links...")
    try:
        links = get_subsector_details(url)
        sector_name, sub_sector = get_sector_names(links)
        st.session_state.sector_name = sector_name
        st.session_state.sub_sector = sub_sector
        add_log(f"Sector: {sector_name}, Sub-sector: {sub_sector}")
    except Exception as e:
        add_log(f"WARNING: Could not extract sector info: {e}")
        st.session_state.sector_name = "Unknown"
        st.session_state.sub_sector = "Unknown"
    return True


def run_step_1():
    """Step 1: Financial data extraction via LLM (checks cache in Sector/ folder first)."""
    add_log("Step 1: Extracting financial data...")
    company_name = st.session_state.company_name
    sub_sector = st.session_state.sub_sector

    # Check cache
    sector_path = os.path.join(SECTOR_DIR, sub_sector)
    file_name = company_name + ".txt"
    full_path = os.path.join(sector_path, file_name)

    if os.path.exists(full_path):
        add_log(f"Found cached data at: {full_path}")
        with open(full_path, "r", encoding="utf-8") as f:
            response = f.read()
    else:
        add_log(
            f"No cache found. Calling LLM ({st.session_state.model_step1})..."
        )
        # BUG FIX: reuse cached site text instead of re-scraping
        up = user_prompt_screener(st.session_state.site_text)
        response = llm(st.session_state.sp_screener, up, st.session_state.model_step1)
        # Save to cache
        os.makedirs(sector_path, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(response)
        add_log(f"Saved to cache: {full_path}")

    st.session_state.result_financial_text = response
    add_log("Step 1 complete.")
    return True


def run_step_2():
    """Step 2: Convert to structured JSON."""
    add_log(f"Step 2: Converting to JSON ({st.session_state.model_step2})...")
    result = llm(
        st.session_state.sp_json,
        create_user_json(st.session_state.result_financial_text),
        st.session_state.model_step2,
    )
    st.session_state.result_financial_json = clean_and_parse_json(result)
    if st.session_state.result_financial_json is None:
        add_log("WARNING: JSON parsing failed. Storing raw text.")
        st.session_state.result_financial_json = result
    else:
        add_log("Step 2 complete. JSON parsed successfully.")
    return True


def run_step_3():
    """Step 3: Generate sector-specific KPIs."""
    add_log(f"Step 3: Generating sector KPIs ({st.session_state.model_step3})...")
    sp = st.session_state.sp_kpi
    up = user_prompts_kpi(st.session_state.sector_name, st.session_state.sub_sector)
    result = llm(sp, up, st.session_state.model_step3)
    st.session_state.result_kpi_json = result
    add_log("Step 3 complete.")
    return True


def run_step_4():
    """Step 4: Extract KPI values via Gemini Search (fallback to calculation)."""
    add_log("Step 4: Extracting KPI values...")
    company_name = st.session_state.company_name
    kpi_json = st.session_state.result_kpi_json

    try:
        add_log("Trying Gemini Search for KPI values...")
        sp = st.session_state.sp_gemini_search
        up = user_prompts_gemini_search(company_name, kpi_json)
        sector_kpis_ratios = gemini_llm_kpi(sp, up, company_name)
        add_log("Gemini Search successful.")
    except Exception as e:
        add_log(f"Gemini Search failed: {e}. Falling back to calculation...")
        sp = st.session_state.sp_kpi_cal
        up = user_prompts_kpi_cal(
            st.session_state.result_financial_json, kpi_json
        )
        sector_kpis_ratios = llm(sp, up, st.session_state.model_step4)

    st.session_state.result_kpi_values = sector_kpis_ratios

    # Clean KPI output
    add_log("Cleaning KPI output...")
    clean_system = (
        "You are a precise financial data extractor. "
        "Read the provided financial summary and output only the numerical values with their field names. "
        "Exclude all fields with N/A, missing values, or descriptive wording. "
        "Return the result strictly in JSON format with key-value pairs."
    )
    clean_user = f"The following is the financial data: {sector_kpis_ratios}"
    st.session_state.result_kpi_values_clean = llm(
        clean_system, clean_user, st.session_state.model_step4
    )
    add_log("Step 4 complete.")
    return True


def run_step_5():
    """Step 5: Final comprehensive analysis."""
    add_log(f"Step 5: Final analysis ({st.session_state.model_step5})...")
    sp = st.session_state.sp_final
    up = create_user_prompt_final(
        st.session_state.company_name,
        st.session_state.sector_name,
        st.session_state.sub_sector,
        st.session_state.result_financial_json,
        st.session_state.result_kpi_values_clean,
    )
    result = llm(sp, up, st.session_state.model_step5)
    st.session_state.result_final_analysis = result

    # Save to file
    file_name = st.session_state.company_name + ".txt"
    full_path = os.path.join(INDIVIDUAL_STOCKS_DIR, file_name)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(result)
    add_log(f"Saved final analysis to: {full_path}")
    add_log("Step 5 complete.")
    return True


def run_step_6():
    """Step 6: Walk the Talk via Gemini Search."""
    add_log("Step 6: Walk the Talk analysis (Gemini Search)...")
    company_name = st.session_state.company_name

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
            model="gemini-3-pro-preview", contents=contents, config=config
        )
        st.session_state.result_walkthetalk = response.text
        add_log("Gemini Search Walk the Talk successful.")
    except Exception as e:
        add_log(f"Gemini Search failed for Walk the Talk: {e}")
        add_log("Falling back to standard LLM call...")
        result = llm(
            "You are a specialized financial data analyst.",
            user_prompt_walkthetalk(company_name),
            st.session_state.model_step6,
        )
        st.session_state.result_walkthetalk = result

    # Save to file
    file_name = company_name + "_concall.txt"
    full_path = os.path.join(INDIVIDUAL_STOCKS_DIR, file_name)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(st.session_state.result_walkthetalk)
    add_log(f"Saved Walk the Talk to: {full_path}")
    add_log("Step 6 complete.")
    return True


def run_step_7():
    """Step 7: Concall credibility scoring."""
    add_log(f"Step 7: Concall credibility scoring ({st.session_state.model_step7})...")
    company_name = st.session_state.company_name
    concall_text = clean_text_for_llm(st.session_state.result_walkthetalk)
    sp = st.session_state.sp_concall_score
    up = prompt_concall_score(company_name, concall_text)
    result = llm(sp, up, st.session_state.model_step7)
    st.session_state.result_concall_score = result

    # Save to file
    file_name = company_name + "_concall_score.txt"
    full_path = os.path.join(INDIVIDUAL_STOCKS_DIR, file_name)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(result)
    add_log(f"Saved Concall Score to: {full_path}")
    add_log("Step 7 complete.")
    return True


STEPS = [
    ("Step 0: Scrape & Extract Metadata", run_step_0),
    ("Step 1: Financial Data Extraction", run_step_1),
    ("Step 2: JSON Conversion", run_step_2),
    ("Step 3: Sector KPI Generation", run_step_3),
    ("Step 4: KPI Value Extraction", run_step_4),
    ("Step 5: Final Comprehensive Analysis", run_step_5),
    ("Step 6: Walk the Talk Analysis", run_step_6),
    ("Step 7: Concall Credibility Score", run_step_7),
]

# Step-by-step mode: show individual run buttons
if st.session_state.step_by_step:
    st.markdown("### Step-by-Step Execution")
    for i, (label, func) in enumerate(STEPS):
        col_btn, col_status = st.columns([1, 3])
        with col_btn:
            step_disabled = False
            # Disable steps that depend on previous uncompleted steps
            if i == 0:
                step_disabled = not st.session_state.url.strip()
            elif i == 1:
                step_disabled = not st.session_state.site_text
            elif i == 2:
                step_disabled = st.session_state.result_financial_text is None
            elif i == 3:
                step_disabled = st.session_state.result_financial_json is None
            elif i == 4:
                step_disabled = st.session_state.result_kpi_json is None
            elif i == 5:
                step_disabled = st.session_state.result_kpi_values_clean is None
            elif i == 6:
                step_disabled = st.session_state.company_name == ""
            elif i == 7:
                step_disabled = st.session_state.result_walkthetalk is None

            if st.button(
                f"▶ {label}",
                key=f"step_btn_{i}",
                disabled=step_disabled,
                use_container_width=True,
            ):
                st.session_state.run_step = i

        with col_status:
            # Show completion status
            result_keys = [
                "site_text",
                "result_financial_text",
                "result_financial_json",
                "result_kpi_json",
                "result_kpi_values_clean",
                "result_final_analysis",
                "result_walkthetalk",
                "result_concall_score",
            ]
            val = st.session_state.get(result_keys[i])
            if val:
                st.success(f"{label} - Done")
            else:
                st.info(f"{label} - Pending")

# Execute a single step if requested
if st.session_state.run_step >= 0:
    step_idx = st.session_state.run_step
    st.session_state.run_step = -1
    label, func = STEPS[step_idx]
    with st.status(f"Running {label}...", expanded=True) as status:
        try:
            success = func()
            if success:
                status.update(label=f"{label} - Complete!", state="complete")
            else:
                status.update(label=f"{label} - Failed", state="error")
        except Exception as e:
            add_log(f"ERROR in {label}: {e}")
            status.update(label=f"{label} - Error: {e}", state="error")
    st.rerun()

# Full pipeline execution
if run_clicked and not st.session_state.step_by_step:
    if not st.session_state.url.strip():
        st.error("Please enter a Screener.in URL in the sidebar.")
    else:
        st.session_state.logs = []
        add_log("Starting full analysis pipeline...")
        progress_bar = st.progress(0, text="Starting...")

        for i, (label, func) in enumerate(STEPS):
            progress_bar.progress(
                (i) / len(STEPS), text=f"Running {label}..."
            )
            with st.status(f"{label}...", expanded=True) as status:
                try:
                    success = func()
                    if success:
                        status.update(
                            label=f"✅ {label}", state="complete"
                        )
                    else:
                        status.update(
                            label=f"❌ {label}", state="error"
                        )
                        add_log(f"Pipeline stopped at {label}.")
                        break
                except Exception as e:
                    add_log(f"ERROR in {label}: {e}")
                    status.update(
                        label=f"❌ {label}: {e}", state="error"
                    )
                    break

        progress_bar.progress(1.0, text="Pipeline complete!")
        add_log("Pipeline finished.")
        st.rerun()


# ============================================================================
# Section 7 - Results Display
# ============================================================================

tab_financial, tab_walkthetalk, tab_score, tab_intermediate, tab_logs = st.tabs(
    [
        "📈 Financial Analysis",
        "🗣 Walk the Talk",
        "📊 Concall Score",
        "🔧 Intermediate Data",
        "📋 Logs",
    ]
)

with tab_financial:
    if st.session_state.result_final_analysis:
        st.markdown(st.session_state.result_final_analysis)
    else:
        st.info("Run the pipeline to see the financial analysis results.")

with tab_walkthetalk:
    if st.session_state.result_walkthetalk:
        st.markdown(st.session_state.result_walkthetalk)
    else:
        st.info("Run the pipeline to see Walk the Talk results.")

with tab_score:
    if st.session_state.result_concall_score:
        st.markdown(st.session_state.result_concall_score)
    else:
        st.info("Run the pipeline to see the Concall Credibility Score.")

with tab_intermediate:
    st.markdown("### Step 1: Scraped Financial Text")
    if st.session_state.result_financial_text:
        with st.expander("View Scraped Data", expanded=False):
            st.text(st.session_state.result_financial_text[:5000] + "..." if len(st.session_state.result_financial_text or "") > 5000 else st.session_state.result_financial_text)
    else:
        st.info("Not yet available.")

    st.markdown("### Step 2: Structured JSON")
    if st.session_state.result_financial_json:
        with st.expander("View JSON Data", expanded=False):
            if isinstance(st.session_state.result_financial_json, dict):
                st.json(st.session_state.result_financial_json)
            else:
                st.text(str(st.session_state.result_financial_json)[:5000])
    else:
        st.info("Not yet available.")

    st.markdown("### Step 3: Sector KPIs")
    if st.session_state.result_kpi_json:
        with st.expander("View KPI JSON", expanded=False):
            st.markdown(st.session_state.result_kpi_json)
    else:
        st.info("Not yet available.")

    st.markdown("### Step 4: KPI Values (Raw)")
    if st.session_state.result_kpi_values:
        with st.expander("View KPI Values", expanded=False):
            st.markdown(st.session_state.result_kpi_values)
    else:
        st.info("Not yet available.")

    st.markdown("### Step 4b: KPI Values (Cleaned)")
    if st.session_state.result_kpi_values_clean:
        with st.expander("View Cleaned KPI Values", expanded=False):
            st.markdown(st.session_state.result_kpi_values_clean)
    else:
        st.info("Not yet available.")

with tab_logs:
    if st.session_state.logs:
        log_text = "\n".join(st.session_state.logs)
        st.code(log_text, language="text")
    else:
        st.info("No logs yet. Run the pipeline to see execution logs.")
