"""
Streamlit Full Sector Screener App
Ports Screener.ipynb pipeline into an interactive web app.
Analyses all companies in a screener.in sector URL.
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
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    override=True,
)

st.set_page_config(
    page_title="Full Sector Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SECTOR_DIR = os.path.join(PROJECT_ROOT, "Sector")
os.makedirs(SECTOR_DIR, exist_ok=True)

# Model constants — loaded from models.json at project root
with open(os.path.join(PROJECT_ROOT, "models.json")) as _f:
    _MODELS_CFG = json.load(_f)
OPENAI_MODEL = _MODELS_CFG["models"]["openai"]
GPT4O = _MODELS_CFG["models"]["gpt4o"]
GEMINI_MODEL = _MODELS_CFG["models"]["gemini"]
MODEL_OPTIONS = _MODELS_CFG["model_options"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
}


# ============================================================================
# Section 1 - Cached Clients
# ============================================================================


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
# Section 2 - Website Class & Utility Functions
# ============================================================================


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
        match = re.search(r"\n\s*(.*?)\n\s*- Screener", self.title)
        if match:
            return match.group(1).strip()
        return self.title

    def get_pages(self):
        raw_text = self.text
        clean_text = raw_text.encode("utf-8").decode("unicode_escape")
        lines = clean_text.splitlines()
        pattern = r"(\d+)\s+results found: Showing page \d+ of (\d+)"
        for line in lines:
            match = re.search(pattern, line)
            if match:
                return int(match.group(2))
        return 1

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
    return None


def llm(system_prompt, user_prompt, model_name):
    match model_name:
        case "gemini":
            gemini_client = get_gemini_client()
            if gemini_client is None:
                raise ValueError("GOOGLE_API_KEY is not set.")
            prompts = build_prompt(system_prompt, user_prompt, "gemini")
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompts}]}],
            )
            return response.candidates[0].content.parts[0].text
        case "openai":
            openai_client = get_openai_client()
            if openai_client is None:
                raise ValueError("OPENAI_API_KEY is not set.")
            prompts = build_prompt(system_prompt, user_prompt, "openai")
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL, messages=prompts
            )
            return response.choices[0].message.content
        case "gpt4o":
            openai_client = get_openai_client()
            if openai_client is None:
                raise ValueError("OPENAI_API_KEY is not set.")
            prompts = build_prompt(system_prompt, user_prompt, "openai")
            response = openai_client.chat.completions.create(
                model=GPT4O, messages=prompts
            )
            return response.choices[0].message.content
        case _:
            return "Unknown model"


def llm_json(system_prompt, user_prompt):
    """Call OpenAI with JSON response format for structured output."""
    openai_client = get_openai_client()
    if openai_client is None:
        raise ValueError("OPENAI_API_KEY is not set.")
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def get_sector_details(url, pages, status_container=None):
    """Get all company links from sector pages."""
    company_links = []
    for i in range(1, pages + 1):
        page_link = url + "?page=" + str(i)
        site = Website(page_link)
        time.sleep(1)
        msg = f"Getting links from page {i} of {pages}"
        add_log(msg)
        if status_container:
            status_container.write(msg)
        for link in site.links:
            if link.startswith("/company/"):
                company_links.append("https://www.screener.in" + link)
    return company_links


def get_company_names(company_links, total_companies, status_container=None):
    """Get company names from their screener links."""
    company_names = []
    for i in range(len(company_links)):
        site = Website(company_links[i])
        time.sleep(1)
        company_names.append(site.title)
        msg = f"Getting company name {i + 1} of {total_companies}"
        add_log(msg)
        if status_container:
            status_container.write(msg)
    company = [title.split(" share price")[0] for title in company_names]
    return company


def get_subsector_details(site):
    """Extract market/sector links from a website."""
    screener_links = []
    for link in site.links:
        if link.startswith("/market/"):
            screener_links.append("https://www.screener.in" + link)
    return screener_links


def get_sector_names(market_links):
    """Get sector and sub-sector names from market links."""
    names = []
    for link in market_links[-2:]:
        site = Website(link)
        time.sleep(1)
        title_text = site.title.strip().split("\n")[0].strip()
        names.append(title_text)
    if len(names) >= 2:
        return names[0], names[1]
    elif len(names) == 1:
        return names[0], names[0]
    return "Unknown", "Unknown"


# ============================================================================
# Section 3 - Default Prompts (from notebook)
# ============================================================================

DEFAULT_SYSTEM_PROMPT_SCREENER = """
You are a financial data extraction AI. Your task is to process text scraped from screener websites and extract all financial information, reproducing it in the exact original format and presentation.

### Core Responsibilities
- **Extract All Financial Data:** Scrape and extract every piece of financial information present in the text.
- **Maintain Original Format:** Preserve the exact formatting, layout, and presentation style, including tables, headings, and hierarchical structures.
- **Preserve Numerical and Textual Integrity:** Keep original numbers, units (e.g., '9 Crores'), percentages, and text styling without any changes.
- **Maintain Grouping:** Replicate the original groupings, sections, and categorizations as they appear on the screener website.

### Data Extraction Categories (Maintain original screener formatting):
- **Company Summary**
- **Key Financial Highlights**
- **Balance Sheet**
- **Cash Flow Statement**
- **Profit & Loss Statement**
- **Financial Ratios**

### Formatting Rules
- **Table Structures:** Recreate tables with proper alignment.
- **Headers:** Keep original headings, subheadings, and section breaks.
- **Indentation:** Preserve indentation levels for sub-items.
- **Number Formatting:** Maintain original number formats (commas, decimals, units).
- **Time Periods:** Use the same time period labels and column headers.
- **Flow and Sequence:** Maintain the original order and flow of information.
- **Special Formatting:** Reproduce any special formatting or emphasis.

### Output
- Present data in plain text, mirroring the screener's visual layout.
- Use appropriate spacing and alignment to recreate tables.
- Include all section headers and subheaders.
- Preserve all footnotes, disclaimers, and notes.

After processing, validate that all data categories and formatting rules have been followed. If any item is missing or formatted incorrectly, revise the output.
"""

DEFAULT_SYSTEM_PROMPT_SCORE = """You are a highly specialized financial analyst with deep expertise in sector-specific company valuation. Your core function is to perform a rigorous, multi-dimensional financial analysis and provide a comprehensive score (0-100) for a given company.

Your analysis must adhere to the following strict principles:
1.  **Exclusive Data Source**: Base your entire analysis ONLY on the financial data provided. You must not access, reference, or supplement with any external financial information, databases, or pre-existing knowledge.
2.  **Sector-Specific Focus**: Tailor your evaluation to the company's sector. Prioritize financial metrics and ratios that are most critical and relevant to that specific industry (e.g., NIM for banking, R&D intensity for technology, asset turnover for manufacturing).
3.  **Holistic Scoring**: Your final score must be the result of a weighted assessment across five key dimensions: Financial Health, Profitability, Growth Quality, Valuation, and Competitive Positioning.
4.  **Methodological Transparency**: Clearly state which metrics you used, how they were weighted, and provide a clear rationale for every conclusion and score.
5.  **Data Limitations**: Explicitly identify any missing or incomplete data and state how this limits the reliability and scope of your analysis. Use conservative assumptions when data is uncertain.

Your responses must be professional, structured, and focused on delivering a clear, data-driven financial assessment. Do not make any mistake or make up data"""

DEFAULT_SYSTEM_PROMPT_JSON = """
You are a financial evaluation assistant. Your task is to analyze a company's financial summary and return a clean, well-formatted JSON response. Use only the data in the input and do not add any commentary outside the JSON.

Your evaluation must include:
1. The company's name
2. Its sector and marketcap
3. A financial attractiveness score (out of 100)
4. The key financial metrics used in deriving that score (as name-value pairs)
5. A short explanation for the score, based on strengths, growth potential, and risk factors

The response must follow this exact JSON structure:

{
  "company": "Company Name",
  "sector": "Sector Name",
  "score": <number>,
  "key_metrics": {
    "Metric1": "Value1",
    "Metric2": "Value2"
  },
  "explanation": "Short explanation"
}

Do not return anything outside the JSON block. Ensure that the JSON is valid and parsable. Do not make any mistake or make up data
"""


def user_prompt_screener(url):
    site = Website(url)
    return f"""
I need you to extract and summarize financial data from a website.

First, provide a brief checklist of the key steps you'll take to extract and format the data.

Next, analyze the following financial data and provide a comprehensive summary:

The contents of this website are as follows:
{site.text}

**Instructions:**
1.  Reproduce the data exactly as it appears on the screener website.
2.  Maintain all table structures, headings, and formatting.
3.  Keep original numerical formats, units, and styling.
4.  Preserve the hierarchical organization and grouping.
5.  Include all relevant financial sections: Company Summary, Key Highlights, Balance Sheet, Cash Flow, P&L, and Ratios.
6.  Maintain the same sequence and flow of information.
7.  Exclude non-financial document sections like Terms of Service or Peer Comparison.

**Expected Output Format:**
Present the extracted data in plain text format that mirrors the screener website's layout, including:
-   Company header information
-   Key metrics in tabular format
-   Financial statements with proper alignment
-   Ratios organized by categories
-   All numerical data with original formatting
-   Time periods and column headers as shown

Ensure the output is in plain text only. Review and validate that all requested financial data is present and correctly formatted. If any section is missing, note it explicitly before continuing.
"""


def user_prompt_score(company_name, sector, financial_summary):
    return f"""
## Financial Analysis Request

### Company Information
- **Company**: {company_name}
- **Sector**: {sector}

### Provided Financial Data
{financial_summary}
### Analysis Instructions

**1. Scoring and Metrics**
- **Overall Score**: Calculate a final score from 0-100.
- **Key Metrics**: Identify and use the 5-7 most relevant financial metrics for the `{sector}` sector to drive your analysis and score.
- **Score Breakdown**: Provide a separate score for each of the following dimensions, explaining the rationale based on the provided data:
    - **Financial Health (25% weight)**: Assess liquidity, solvency, and capital structure (e.g., Debt/Equity, Cash).
    - **Profitability (25% weight)**: Evaluate margins, returns, and efficiency (e.g., ROE, ROA, Operating Profit Margin).
    - **Growth Quality (20% weight)**: Analyze revenue and earnings growth and their sustainability (e.g., Sales Growth, Profit Growth).
    - **Valuation (15% weight)**: Examine trading multiples against sector norms (e.g., P/E, P/B).
    - **Competitive Position (15% weight)**: Infer competitive advantages from financial data (e.g., stable margins, high returns).

**2. Data Handling Requirements**
- **Exclusivity**: Your analysis is strictly limited to the data provided in the `Provided Financial Data` block.
- **Ratios**: If a ratio is present in the provided data (e.g., `Sales Growth`, `ROE`), use it directly. If you calculate a new ratio from the raw numbers, clearly label it as `[CALCULATED]`.
- **Missing Data**: If a metric required for the analysis is not present, state "INSUFFICIENT DATA" and explain how its absence affects your assessment.

**3. Final Output Format**
- **OVERALL SCORE**: X/100
- **RATIONALE**: A concise summary of the primary factors influencing the final score.
- **KEY METRICS TABLE**: A table or list presenting the 5-7 key metrics, their values, and a brief note on their significance for the `{sector}` sector.
- **ANALYSIS SUMMARY**:
    - **Strengths**: List 3-4 key financial strengths with specific metric references.
    - **Risks**: Identify 3-4 primary financial and sector-specific risks.
    - **Investment Thesis**: A 2-3 sentence summary of the investment case and its confidence level.
- **DATA ASSESSMENT**:
    - **Completeness**: Comment on the completeness of the provided financial data.
    - **Confidence**: State your confidence level in the analysis, which is directly tied to the completeness of the data.
"""


def user_prompt_json(result):
    return (
        "Please extract and convert the following company analysis into JSON format as per the given structure:\n"
        + result
    )


# ============================================================================
# Section 4 - Session State Init
# ============================================================================

DEFAULTS = {
    "url": "",
    "sector": "",
    "sector_name": "",
    "sub_sector": "",
    "pages": 0,
    "company_links": [],
    "company_list": [],
    "company_dict": {},
    "total_companies": 0,
    "folder_path": "",
    # Model choices
    "model_screener": "gemini",
    "model_score": "gemini",
    # Editable prompts
    "sp_screener": DEFAULT_SYSTEM_PROMPT_SCREENER,
    "sp_score": DEFAULT_SYSTEM_PROMPT_SCORE,
    "sp_json": DEFAULT_SYSTEM_PROMPT_JSON,
    # Pipeline phase tracking
    "phase": "idle",  # idle, scraping, analysing, scoring, json_creating, done
    "current_company_idx": 0,
    "score_idx": 0,
    "json_idx": 0,
    # Results
    "final_results_json": [],
    "score_df": None,
    # Logs
    "logs": [],
    # Execution flags
    "run_pipeline": False,
    "stop_requested": False,
}

for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ============================================================================
# Section 5 - Sidebar
# ============================================================================

with st.sidebar:
    st.title("📊 Full Sector Screener")
    st.markdown("---")

    st.session_state.url = st.text_input(
        "Screener.in Sector URL",
        value=st.session_state.url,
        placeholder="https://www.screener.in/market/IN06/IN0601/IN060103/IN060103001/",
    )

    # API status
    st.markdown("### API Status")
    if "api_status" not in st.session_state:
        test_sp = "You are an AI assistant"
        test_up = "Respond with your model name only"
        st.session_state.api_status = {}
        for model_label, model_key in [
            ("OpenAI", "openai"),
            ("GPT-4o", "gpt4o"),
            ("Gemini", "gemini"),
        ]:
            try:
                llm(test_sp, test_up, model_key)
                st.session_state.api_status[model_label] = True
            except Exception:
                st.session_state.api_status[model_label] = False

    for model_label, ok in st.session_state.api_status.items():
        if ok:
            st.success(f"{model_label}: Connected")
        else:
            st.error(f"{model_label}: Failed")

    st.markdown("---")
    st.markdown("### Model Selection")

    st.session_state.model_screener = st.selectbox(
        "Financial Data Extraction Model",
        MODEL_OPTIONS,
        index=MODEL_OPTIONS.index(st.session_state.model_screener),
        key="sel_model_screener",
    )
    st.session_state.model_score = st.selectbox(
        "Score Calculation Model",
        MODEL_OPTIONS,
        index=MODEL_OPTIONS.index(st.session_state.model_score),
        key="sel_model_score",
    )

    st.markdown("---")

    col_run, col_reset = st.columns(2)
    with col_run:
        run_clicked = st.button(
            "🚀 Run Analysis", use_container_width=True, type="primary"
        )
    with col_reset:
        if st.button("🔄 Reset All", use_container_width=True):
            for key, val in DEFAULTS.items():
                st.session_state[key] = val
            st.rerun()


# ============================================================================
# Section 6 - Main Display
# ============================================================================

st.title("Full Sector Screener Pipeline")

# Info bar — responsive layout for long titles
if st.session_state.sector:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Sector:** {st.session_state.sector}")
        st.markdown(f"**Category:** {st.session_state.sector_name}")
    with col2:
        st.markdown(f"**Sub-Category:** {st.session_state.sub_sector}")
        st.markdown(f"**Total Companies:** {st.session_state.total_companies}")

# Edit Prompts (main page expander)
with st.expander("📝 Edit System Prompts", expanded=False):
    prompt_tab1, prompt_tab2, prompt_tab3 = st.tabs(
        ["Screener Extraction", "Score Calculation", "JSON Conversion"]
    )
    with prompt_tab1:
        st.session_state.sp_screener = st.text_area(
            "Screener System Prompt",
            value=st.session_state.sp_screener,
            height=250,
            key="ta_sp_screener",
        )
    with prompt_tab2:
        st.session_state.sp_score = st.text_area(
            "Score System Prompt",
            value=st.session_state.sp_score,
            height=250,
            key="ta_sp_score",
        )
    with prompt_tab3:
        st.session_state.sp_json = st.text_area(
            "JSON System Prompt",
            value=st.session_state.sp_json,
            height=250,
            key="ta_sp_json",
        )
    if st.button("Reset Prompts to Defaults"):
        st.session_state.sp_screener = DEFAULT_SYSTEM_PROMPT_SCREENER
        st.session_state.sp_score = DEFAULT_SYSTEM_PROMPT_SCORE
        st.session_state.sp_json = DEFAULT_SYSTEM_PROMPT_JSON
        st.rerun()

# Tabs for results
tab_status, tab_scores, tab_companies, tab_logs = st.tabs(
    ["📡 Execution Status", "📊 Final Scores", "🏢 Company Details", "📋 Logs"]
)

# ============================================================================
# Section 7 - Pipeline Execution
# ============================================================================

if run_clicked:
    url = st.session_state.url.strip()
    if not url:
        st.error("Please enter a Screener.in sector URL in the sidebar.")
    else:
        st.session_state.logs = []
        st.session_state.final_results_json = []
        st.session_state.score_df = None

        with tab_status:
            # ── Phase 1: Scrape sector info ──
            with st.status("Phase 1: Scraping sector information...", expanded=True) as phase1:
                st.write("Connecting to Screener.in...")
                add_log("Phase 1: Scraping sector URL...")

                try:
                    site = Website(url)
                    pages = site.get_pages()
                    sector = site.get_title()

                    st.session_state.pages = pages
                    st.session_state.sector = sector

                    st.write(f"**Analysing:** {sector}")
                    st.write(f"**Total pages to be analysed:** {pages}")
                    add_log(f"Analysing: {sector}")
                    add_log(f"Total pages to be analysed: {pages}")

                    # Create folder for sector
                    base_path = SECTOR_DIR
                    try:
                        folder_path = os.path.join(base_path, sector)
                        os.makedirs(folder_path, exist_ok=True)
                    except Exception:
                        safe_name = re.sub(r'[<>:"/\\|?*;]', "_", sector)
                        folder_path = os.path.join(base_path, safe_name)
                        os.makedirs(folder_path, exist_ok=True)
                    st.session_state.folder_path = folder_path
                    add_log(f"Folder created at: {folder_path}")

                    phase1.update(label="Phase 1: Sector info scraped", state="complete")
                except Exception as e:
                    add_log(f"ERROR in Phase 1: {e}")
                    phase1.update(label=f"Phase 1: Failed - {e}", state="error")
                    st.stop()

            # ── Phase 2: Get company links ──
            with st.status("Phase 2: Getting company links...", expanded=True) as phase2:
                try:
                    company_links = get_sector_details(url, pages, phase2)
                    total_companies = len(company_links)
                    st.session_state.company_links = company_links
                    st.session_state.total_companies = total_companies

                    st.write(f"**Total companies to analyse:** {total_companies}")
                    add_log(f"Total companies to analyse: {total_companies}")

                    phase2.update(label=f"Phase 2: Found {total_companies} companies", state="complete")
                except Exception as e:
                    add_log(f"ERROR in Phase 2: {e}")
                    phase2.update(label=f"Phase 2: Failed - {e}", state="error")
                    st.stop()

            # ── Phase 3: Get company names ──
            with st.status("Phase 3: Getting company names...", expanded=True) as phase3:
                try:
                    company_list = get_company_names(
                        company_links, total_companies, phase3
                    )
                    st.session_state.company_list = company_list

                    company_dict = dict(zip(company_list, company_links))
                    st.session_state.company_dict = company_dict

                    st.write("**Companies found:**")
                    st.write(", ".join(company_list))
                    add_log(f"Company list: {company_list}")

                    phase3.update(label=f"Phase 3: Named {len(company_list)} companies", state="complete")
                except Exception as e:
                    add_log(f"ERROR in Phase 3: {e}")
                    phase3.update(label=f"Phase 3: Failed - {e}", state="error")
                    st.stop()

            # ── Phase 4: Get sector & sub-sector names ──
            with st.status("Phase 4: Getting sector classification...", expanded=True) as phase4:
                try:
                    last_company_site = Website(company_links[-1])
                    market_links = get_subsector_details(last_company_site)
                    sector_name, sub_sector = get_sector_names(market_links)
                    st.session_state.sector_name = sector_name
                    st.session_state.sub_sector = sub_sector

                    st.write(f"**Analysing Sector:** {sector_name}")
                    st.write(f"**Subcategory:** {sub_sector}")
                    add_log(f"Analysing Sector: {sector_name}, Subcategory: {sub_sector}")

                    phase4.update(label="Phase 4: Sector classification done", state="complete")
                except Exception as e:
                    add_log(f"ERROR in Phase 4: {e}")
                    phase4.update(label=f"Phase 4: Failed - {e}", state="error")
                    st.stop()

            # ── Phase 5: Financial data extraction for each company ──
            folder_path = st.session_state.folder_path
            with st.status("Phase 5: Extracting financial data for all companies...", expanded=True) as phase5:
                progress_bar = st.progress(0, text="Starting financial extraction...")
                max_runs = 100
                run_count = 0

                for i in range(len(company_links)):
                    if run_count >= max_runs:
                        break

                    file_name = company_list[i] + ".txt"
                    full_path = os.path.join(folder_path, file_name)

                    if not os.path.exists(full_path):
                        msg = f"Analysing {company_list[i]} on {company_links[i]}. Currently on {i + 1} out of {total_companies}"
                        st.write(msg)
                        add_log(msg)
                        progress_bar.progress(
                            (i + 1) / total_companies,
                            text=f"Extracting: {company_list[i]} ({i + 1}/{total_companies})",
                        )

                        time.sleep(1)
                        try:
                            result = llm(
                                st.session_state.sp_screener,
                                user_prompt_screener(company_links[i]),
                                st.session_state.model_screener,
                            )
                            with open(full_path, "w", encoding="utf-8") as f:
                                f.write(result)
                            add_log(f"Saved {company_list[i]} data to {full_path}")
                            run_count += 1
                        except Exception as e:
                            add_log(f"ERROR extracting {company_list[i]}: {e}")
                            st.write(f"⚠️ Error extracting {company_list[i]}: {e}")
                    else:
                        msg = f"Skipped writing {company_list[i]} — file already exists at {full_path}"
                        st.write(msg)
                        add_log(msg)
                        progress_bar.progress(
                            (i + 1) / total_companies,
                            text=f"Skipped (cached): {company_list[i]}",
                        )

                progress_bar.progress(1.0, text="Financial extraction complete!")
                phase5.update(label=f"Phase 5: Extracted data for {total_companies} companies", state="complete")

            # ── Phase 6: Score calculation ──
            with st.status("Phase 6: Calculating scores for all companies...", expanded=True) as phase6:
                # Read all txt files
                file_names = []
                file_contents = []
                for filename in os.listdir(folder_path):
                    if filename.endswith(".txt") and not filename.endswith("_Score.txt"):
                        file_path_full = os.path.join(folder_path, filename)
                        try:
                            with open(file_path_full, "r", encoding="utf-8") as f:
                                content = f.read()
                            base_name = os.path.splitext(filename)[0]
                            file_names.append(base_name)
                            file_contents.append(content)
                        except Exception as e:
                            add_log(f"Error reading {file_path_full}: {e}")

                progress_bar2 = st.progress(0, text="Starting score calculation...")

                for i in range(len(file_names)):
                    base_name = file_names[i]
                    score_file_name = base_name + "_Score.txt"
                    score_full_path = os.path.join(folder_path, score_file_name)

                    # Check file size - skip if > 20KB (likely already a score file)
                    source_path = os.path.join(folder_path, base_name + ".txt")
                    size_kb = os.path.getsize(source_path) / 1024 if os.path.exists(source_path) else 0

                    if os.path.exists(score_full_path) or size_kb > 20:
                        msg = f"Skipping {score_file_name}, already exists."
                        st.write(msg)
                        add_log(msg)
                        progress_bar2.progress(
                            (i + 1) / len(file_names),
                            text=f"Skipped: {base_name}",
                        )
                        continue

                    msg = f"Score Calculating for {file_names[i]}"
                    st.write(msg)
                    add_log(msg)
                    progress_bar2.progress(
                        (i + 1) / len(file_names),
                        text=f"Scoring: {file_names[i]} ({i + 1}/{len(file_names)})",
                    )

                    try:
                        up = user_prompt_score(file_names[i], sector, file_contents[i])
                        result = llm(
                            st.session_state.sp_score,
                            up,
                            st.session_state.model_score,
                        )
                        time.sleep(1)
                        with open(score_full_path, "w", encoding="utf-8") as f:
                            f.write(result)
                        add_log(f"Saved score for {file_names[i]}")
                    except Exception as e:
                        add_log(f"ERROR scoring {file_names[i]}: {e}")
                        st.write(f"⚠️ Error scoring {file_names[i]}: {e}")

                progress_bar2.progress(1.0, text="Score calculation complete!")
                phase6.update(label=f"Phase 6: Scored {len(file_names)} companies", state="complete")

            # ── Phase 7: JSON creation ──
            with st.status("Phase 7: Creating structured JSON summaries...", expanded=True) as phase7:
                # Re-read score files
                score_file_names = []
                score_file_contents = []
                for filename in os.listdir(folder_path):
                    if filename.endswith("_Score.txt"):
                        file_path_full = os.path.join(folder_path, filename)
                        try:
                            with open(file_path_full, "r", encoding="utf-8") as f:
                                content = f.read()
                            base_name = os.path.splitext(filename)[0]
                            score_file_names.append(base_name)
                            score_file_contents.append(content)
                        except Exception as e:
                            add_log(f"Error reading {file_path_full}: {e}")

                # Progress file for resumability
                progress_file = os.path.join(folder_path, "progress.json")
                if os.path.exists(progress_file):
                    with open(progress_file, "r") as f:
                        final_results = json.load(f)
                    add_log(f"Resumed from existing progress. Already processed: {len(final_results)} files")
                else:
                    final_results = []

                start_index = len(final_results)
                progress_bar3 = st.progress(
                    start_index / max(len(score_file_names), 1),
                    text="Starting JSON creation...",
                )

                for i in range(start_index, len(score_file_names)):
                    msg = f"JSON Creation for {score_file_names[i]}"
                    st.write(msg)
                    add_log(msg)
                    progress_bar3.progress(
                        (i + 1) / len(score_file_names),
                        text=f"JSON: {score_file_names[i]} ({i + 1}/{len(score_file_names)})",
                    )

                    try:
                        up = user_prompt_json(score_file_contents[i])
                        content = llm_json(st.session_state.sp_json, up)
                        final_temp = json.loads(content)
                        final_results.append(final_temp)

                        # Save progress
                        with open(progress_file, "w") as f:
                            json.dump(final_results, f, indent=2)
                        add_log(f"Successfully processed: {score_file_names[i]}")
                    except Exception as e:
                        add_log(f"ERROR JSON for {score_file_names[i]}: {e}")
                        st.write(f"⚠️ Error creating JSON for {score_file_names[i]}: {e}")

                st.session_state.final_results_json = final_results
                progress_bar3.progress(1.0, text="JSON creation complete!")
                phase7.update(label=f"Phase 7: Created JSON for {len(final_results)} companies", state="complete")

            # ── Phase 8: Save final files (JSON, CSV) and build score dataframe ──
            with st.status("Phase 8: Saving final results...", expanded=True) as phase8:
                try:
                    # Save sector JSON
                    json_file_name = sector + ".json"
                    try:
                        json_full_path = os.path.join(folder_path, json_file_name)
                        with open(json_full_path, "w", encoding="utf-8") as json_file:
                            json.dump(final_results, json_file, ensure_ascii=False, indent=2)
                        add_log(f"File saved to {json_full_path}")
                    except Exception:
                        safe_name = re.sub(r'[<>:"/\\|?*;]', "_", sector)
                        json_full_path = os.path.join(folder_path, safe_name + ".json")
                        with open(json_full_path, "w", encoding="utf-8") as json_file:
                            json.dump(final_results, json_file, ensure_ascii=False, indent=2)
                        add_log(f"File saved to {json_full_path}")

                    st.write(f"Saved JSON: {json_full_path}")

                    # Build dataframe
                    if final_results:
                        df = pd.DataFrame(final_results)
                        score_df = df[["company", "score"]].copy()
                        score_df["Sector"] = sector
                        score_df["url"] = score_df["company"].map(
                            st.session_state.company_dict
                        )
                        score_df = score_df.sort_values(by="score", ascending=False)
                        st.session_state.score_df = score_df

                        # Save CSV
                        csv_file_name = sector + ".csv"
                        try:
                            csv_full_path = os.path.join(folder_path, csv_file_name)
                            score_df.to_csv(csv_full_path, index=False, encoding="utf-8-sig")
                            add_log(f"CSV saved to {csv_full_path}")
                        except Exception:
                            safe_name = re.sub(r'[<>:"/\\|?*;]', "_", sector)
                            csv_full_path = os.path.join(folder_path, safe_name + ".csv")
                            score_df.to_csv(csv_full_path, index=False, encoding="utf-8-sig")
                            add_log(f"CSV saved to {csv_full_path}")

                        st.write(f"Saved CSV: {csv_full_path}")

                    phase8.update(label="Phase 8: All files saved!", state="complete")
                    add_log("Pipeline completed successfully!")
                except Exception as e:
                    add_log(f"ERROR in Phase 8: {e}")
                    phase8.update(label=f"Phase 8: Failed - {e}", state="error")

        st.rerun()


# ============================================================================
# Section 8 - Results Display (persists across reruns)
# ============================================================================

with tab_scores:
    if st.session_state.score_df is not None:
        score_df = st.session_state.score_df

        st.markdown(f"### {st.session_state.sector} - Company Scores")
        st.markdown(f"**Sector:** {st.session_state.sector_name} | **Sub-Category:** {st.session_state.sub_sector}")

        # Score summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Companies", len(score_df))
        col2.metric("Avg Score", f"{score_df['score'].mean():.1f}")
        col3.metric("Top Score", f"{score_df['score'].max()}")
        col4.metric("Lowest Score", f"{score_df['score'].min()}")

        st.markdown("---")

        # Color-coded dataframe
        def color_score(val):
            if val >= 75:
                return "background-color: #2d6a4f; color: white"
            elif val >= 60:
                return "background-color: #52b788; color: white"
            elif val >= 40:
                return "background-color: #f4a261; color: black"
            else:
                return "background-color: #e76f51; color: white"

        styled_df = score_df.style.applymap(color_score, subset=["score"])
        st.dataframe(
            styled_df,
            use_container_width=True,
            height=min(len(score_df) * 40 + 40, 600),
        )

        # Bar chart
        st.markdown("### Score Distribution")
        chart_df = score_df[["company", "score"]].set_index("company")
        st.bar_chart(chart_df, horizontal=True, height=max(len(score_df) * 25, 400))

    else:
        st.info("Run the pipeline to see final scores here.")

with tab_companies:
    if st.session_state.final_results_json:
        st.markdown("### Individual Company Analysis")

        for entry in st.session_state.final_results_json:
            company = entry.get("company", "Unknown")
            score = entry.get("score", "N/A")
            explanation = entry.get("explanation", "")
            metrics = entry.get("key_metrics", {})
            sector_label = entry.get("sector", "")

            with st.expander(f"**{company}** — Score: {score}/100", expanded=False):
                st.markdown(f"**Sector:** {sector_label}")
                st.markdown(f"**Score:** {score}/100")
                st.markdown(f"**Explanation:** {explanation}")
                if metrics:
                    st.markdown("**Key Metrics:**")
                    metrics_df = pd.DataFrame(
                        list(metrics.items()), columns=["Metric", "Value"]
                    )
                    st.table(metrics_df)
    else:
        st.info("Run the pipeline to see company details here.")

with tab_logs:
    if st.session_state.logs:
        log_text = "\n".join(st.session_state.logs)
        st.code(log_text, language="text")
    else:
        st.info("No logs yet. Run the pipeline to see execution logs.")
