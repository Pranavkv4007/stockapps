"""
Individual Stock Score Visualizer
Combines financial (Overall) and concall (Credibility) scores from
Individual_Stocks folder and displays them interactively.
Replicates and improves StocksCObine.ipynb logic.
"""

import os
import re
import json
import math
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ============================================================================
# Config
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
INDIVIDUAL_DIR = os.path.join(PROJECT_ROOT, "Individual_Stocks")
SCORES_JSON = os.path.join(PROJECT_ROOT, "scores.json")

st.set_page_config(
    page_title="Individual Stock Scores",
    page_icon="\U0001F4C8",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# Score Extraction (from StocksCObine.ipynb)
# ============================================================================


def extract_overall_score(file_path):
    """Extract Overall Score from a financial analysis txt file.
    Handles multiple LLM output formats:
      - '## Overall Score: 78 / 100'
      - '# 1. Overall Financial Health Score: **84 / 100**'
      - '"score": 85,'  or '"Overall Score": 80,'
      - '| **Total** | 100% | **78** |'
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pass 1: Lines containing "overall score" with N/100
        for line in content.split("\n"):
            if "overall score" in line.lower() or "overall financial health score" in line.lower():
                match = re.search(r"(\d+)\s*/\s*100", line)
                if match:
                    return int(match.group(1))

        # Pass 2: JSON-style "score": 85 or "Overall Score": 80 (near top of file)
        # Only check first 30 lines to avoid picking up sub-scores
        top_lines = "\n".join(content.split("\n")[:30])
        match = re.search(r'"(?:score|Overall Score)"\s*:\s*(\d+)', top_lines)
        if match:
            score = int(match.group(1))
            if 0 <= score <= 100:
                return score

        # Pass 3: Table composite row like '| **Overall Composite Score** | 100% | - | **85** |'
        match = re.search(
            r"overall composite score.*?\*\*(\d+)\*\*", content, re.IGNORECASE
        )
        if match:
            return int(match.group(1))

        # Pass 4: '| **Total** | 100% | **78** |'
        match = re.search(
            r"\|\s*\*{0,2}Total\*{0,2}\s*\|.*?\*{0,2}(\d+)\*{0,2}\s*\|",
            content, re.IGNORECASE,
        )
        if match:
            score = int(match.group(1))
            if 0 < score <= 100:
                return score

        return None
    except Exception:
        return None


def extract_credibility_score(file_path):
    """Extract credibility score from a concall_score txt file.
    Handles multiple LLM output formats."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        patterns = [
            # "credibility score: 55 / 100" or "credibility score: 55/100"
            r"credibility score[:\s*|]+\*{0,2}\s*(?:dYY.|dYY.|dY..?)?\s*\*{0,2}\s*(\d+(?:\.\d+)?)\s*/\s*100",
            # "credibility score: 55 (..." or "credibility score: 55\n"
            r"credibility score[:\s*|]+\*{0,2}\s*(?:dYY.|dYY.|dY..?)?\s*\*{0,2}\s*(\d+(?:\.\d+)?)\s*(?:\(|$|\s)",
            # Table format with pipes: "| **55 (Moderate)**"
            r"\|\s*\*{0,2}\s*(\d+(?:\.\d+)?)\s*(?:\(|\|)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                score = float(match.group(1))
                if 0 <= score <= 100:
                    return round(score, 1)
        return None
    except Exception:
        return None


# ============================================================================
# Data Loading — combines both score types
# ============================================================================


@st.cache_data
def load_individual_scores():
    """Scan Individual_Stocks folder, extract both score types,
    save scores.json (overwrite), and return a DataFrame."""

    if not os.path.isdir(INDIVIDUAL_DIR):
        return pd.DataFrame()

    overall_scores = {}
    credibility_scores = {}
    skipped_overall = []
    skipped_credibility = []

    for filename in sorted(os.listdir(INDIVIDUAL_DIR)):
        filepath = os.path.join(INDIVIDUAL_DIR, filename)

        # Overall score files: *.txt without underscores in the name
        if filename.endswith(".txt") and "_" not in filename.replace(".txt", ""):
            company = filename.replace(".txt", "")
            score = extract_overall_score(filepath)
            if score is not None:
                overall_scores[company] = score
            else:
                skipped_overall.append(company)

        # Credibility score files: *_concall_score.txt
        elif filename.endswith("_concall_score.txt"):
            company = filename.replace("_concall_score.txt", "")
            score = extract_credibility_score(filepath)
            if score is not None:
                credibility_scores[company] = score
            else:
                skipped_credibility.append(company)

    # Save scores.json (always overwrite)
    results = {
        "overall_scores": overall_scores,
        "credibility_scores": credibility_scores,
    }
    with open(SCORES_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Merge into a single DataFrame
    all_companies = sorted(set(overall_scores.keys()) | set(credibility_scores.keys()))
    records = []
    for company in all_companies:
        overall = overall_scores.get(company)
        credibility = credibility_scores.get(company)
        records.append(
            {
                "Company": company,
                "Financial Score": overall,
                "Concall Score": credibility,
            }
        )

    df = pd.DataFrame(records)

    # Compute combined score where both exist (equal weight)
    df["Combined Score"] = df.apply(
        lambda r: round((r["Financial Score"] + r["Concall Score"]) / 2, 1)
        if pd.notna(r["Financial Score"]) and pd.notna(r["Concall Score"])
        else None,
        axis=1,
    )

    return df


# ============================================================================
# Load data
# ============================================================================

df = load_individual_scores()

if df.empty:
    st.error(
        "No Individual_Stocks folder found or no score files detected. "
        "Run the individual stock analysis pipeline first."
    )
    st.stop()

# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.title("\U0001F50D Filters")

    # Score type filter
    score_col = st.radio(
        "Score to Analyse",
        ["Combined Score", "Financial Score", "Concall Score"],
        index=0,
    )

    # Score range — only for rows where chosen score exists
    valid = df[df[score_col].notna()]
    if valid.empty:
        st.warning(f"No companies have a {score_col}.")
        st.stop()

    s_min, s_max = int(valid[score_col].min()), int(valid[score_col].max())
    default_floor = max(math.floor(s_max / 10) * 10, s_min)
    score_range = st.slider(
        "Score Range",
        min_value=s_min,
        max_value=s_max,
        value=(s_min, s_max),
    )

    show_top_n = st.slider("Show Top N", min_value=1, max_value=len(valid), value=min(15, len(valid)))

    st.markdown("---")
    if st.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption(
        f"Total companies: {len(df)} | "
        f"With Financial Score: {df['Financial Score'].notna().sum()} | "
        f"With Concall Score: {df['Concall Score'].notna().sum()}"
    )

# Apply filters
filtered = valid[
    (valid[score_col] >= score_range[0]) & (valid[score_col] <= score_range[1])
].sort_values(score_col, ascending=False)

# ============================================================================
# Helper
# ============================================================================


def read_file_content(company, suffix=""):
    """Read a file from INDIVIDUAL_DIR. suffix examples: '', '_concall', '_concall_score'."""
    fname = f"{company}{suffix}.txt"
    fpath = os.path.join(INDIVIDUAL_DIR, fname)
    if os.path.isfile(fpath):
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return None


def score_color(val):
    try:
        val = float(val)
    except (TypeError, ValueError):
        return ""
    if val >= 80:
        return "background-color: #2d6a4f; color: white"
    elif val >= 60:
        return "background-color: #52b788; color: white"
    elif val >= 40:
        return "background-color: #f4a261; color: black"
    return "background-color: #e76f51; color: white"


# ============================================================================
# Header KPIs
# ============================================================================

st.title("Individual Stock Scores")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Companies", len(filtered))
k2.metric(f"Avg {score_col}", f"{filtered[score_col].mean():.1f}" if not filtered.empty else "\u2014")
k3.metric(f"Top {score_col}", f"{filtered[score_col].max():.0f}" if not filtered.empty else "\u2014")
k4.metric("Missing Scores", int(df["Combined Score"].isna().sum()))

st.markdown("---")

# ============================================================================
# Tabs
# ============================================================================

tab_overview, tab_compare, tab_leaderboard, tab_data = st.tabs(
    ["Overview", "Score Comparison", "Leaderboard", "Raw Data"]
)

# ── Helper: computed columns for stock selection ─────────────────────────────


def assign_tier(score):
    """Map a numeric score to a human-readable tier label."""
    if score is None or pd.isna(score):
        return "\u2014"
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Average"
    return "Weak"


def assign_signal(fin, con):
    """Derive a buy-signal verdict from both scores."""
    has_fin = fin is not None and not pd.isna(fin)
    has_con = con is not None and not pd.isna(con)

    if has_fin and has_con:
        if fin >= 75 and con >= 75:
            return "Strong Buy"
        if fin >= 75 and con < 60:
            return "Financials Strong, Concall Weak"
        if con >= 75 and fin < 60:
            return "Concall Strong, Financials Weak"
        if fin >= 60 and con >= 60:
            return "Moderate Buy"
        if fin < 50 and con < 50:
            return "Avoid"
        return "Mixed"
    if has_fin:
        return "Concall Missing"
    if has_con:
        return "Financials Missing"
    return "\u2014"


def signal_color(val):
    """Color code the signal cell."""
    colors = {
        "Strong Buy": "background-color: #2d6a4f; color: white",
        "Moderate Buy": "background-color: #52b788; color: white",
        "Mixed": "background-color: #f4a261; color: black",
        "Avoid": "background-color: #e76f51; color: white",
        "Financials Strong, Concall Weak": "background-color: #e9c46a; color: black",
        "Concall Strong, Financials Weak": "background-color: #e9c46a; color: black",
        "Concall Missing": "background-color: #adb5bd; color: black",
        "Financials Missing": "background-color: #adb5bd; color: black",
    }
    return colors.get(val, "")


def tier_color(val):
    """Color code tier labels."""
    colors = {
        "Excellent": "background-color: #2d6a4f; color: white",
        "Good": "background-color: #52b788; color: white",
        "Average": "background-color: #f4a261; color: black",
        "Weak": "background-color: #e76f51; color: white",
    }
    return colors.get(val, "")


# ── Overview ─────────────────────────────────────────────────────────────────
with tab_overview:
    if filtered.empty:
        st.info("No companies match the current filters.")
    else:
        st.subheader(f"Top {show_top_n} Stocks \u2014 Ranked by {score_col}")

        overview = filtered.head(show_top_n).copy()
        overview.insert(0, "Rank", range(1, len(overview) + 1))
        overview["Tier"] = overview[score_col].apply(assign_tier)
        overview["Signal"] = overview.apply(
            lambda r: assign_signal(r.get("Financial Score"), r.get("Concall Score")), axis=1
        )

        # Build display table
        display_cols = ["Rank", "Company", "Financial Score", "Concall Score", "Combined Score", "Tier", "Signal"]
        ov_display = overview[display_cols].reset_index(drop=True)

        score_subset = ["Financial Score", "Concall Score", "Combined Score"]
        styled_ov = (
            ov_display.style
            .applymap(score_color, subset=score_subset)
            .applymap(tier_color, subset=["Tier"])
            .applymap(signal_color, subset=["Signal"])
        )
        st.dataframe(styled_ov, use_container_width=True, hide_index=True,
                      height=min(len(ov_display) * 40 + 45, 700))

        # Signal legend
        st.markdown("---")
        st.caption(
            "**Signal guide:** "
            "Strong Buy = both scores >= 75 | "
            "Moderate Buy = both >= 60 | "
            "Mixed = scores disagree | "
            "Avoid = both < 50 | "
            "Grey = one score missing"
        )

        # Tier summary counts
        st.markdown("#### Tier Summary")
        tier_summary = (
            filtered[score_col]
            .apply(assign_tier)
            .value_counts()
            .reindex(["Excellent", "Good", "Average", "Weak"], fill_value=0)
            .reset_index()
        )
        tier_summary.columns = ["Tier", "Companies"]
        styled_tier = tier_summary.style.applymap(tier_color, subset=["Tier"])
        st.dataframe(styled_tier, use_container_width=True, hide_index=True)

# ── Score Comparison ─────────────────────────────────────────────────────────
with tab_compare:
    both = df.dropna(subset=["Financial Score", "Concall Score"]).copy()

    if both.empty:
        st.info("No companies have both Financial and Concall scores to compare.")
    else:
        both["Gap"] = (both["Financial Score"] - both["Concall Score"]).round(1)
        both["Abs Gap"] = both["Gap"].abs()
        both["Stronger"] = both["Gap"].apply(
            lambda g: "Financials" if g > 5 else ("Concall" if g < -5 else "Balanced")
        )
        both["Signal"] = both.apply(
            lambda r: assign_signal(r.get("Financial Score"), r.get("Concall Score")), axis=1
        )
        both = both.sort_values("Combined Score", ascending=False)
        both.insert(0, "Rank", range(1, len(both) + 1))

        # ── Aligned Stocks: both scores agree (gap <= 10) ────────────────────
        st.subheader("Aligned Stocks \u2014 Scores Within 10 Points")
        st.caption("Both financial data and management credibility tell the same story. High confidence in the score.")
        aligned = both[both["Abs Gap"] <= 10].copy()
        if aligned.empty:
            st.info("No aligned stocks found.")
        else:
            aligned_display = aligned[
                ["Rank", "Company", "Financial Score", "Concall Score",
                 "Combined Score", "Gap", "Signal"]
            ].reset_index(drop=True)
            styled_aligned = (
                aligned_display.style
                .applymap(score_color, subset=["Financial Score", "Concall Score", "Combined Score"])
                .applymap(signal_color, subset=["Signal"])
            )
            st.dataframe(styled_aligned, use_container_width=True, hide_index=True,
                          height=min(len(aligned_display) * 40 + 45, 500))

        # ── Divergent Stocks: scores disagree (gap > 10) ─────────────────────
        st.markdown("---")
        st.subheader("Divergent Stocks \u2014 Gap > 10 Points")
        st.caption(
            "Scores disagree significantly. Investigate further before deciding. "
            "Positive gap = Financials stronger. Negative gap = Concall stronger."
        )
        divergent = both[both["Abs Gap"] > 10].sort_values("Abs Gap", ascending=False).copy()
        if divergent.empty:
            st.info("No divergent stocks found.")
        else:
            div_display = divergent[
                ["Rank", "Company", "Financial Score", "Concall Score",
                 "Combined Score", "Gap", "Stronger", "Signal"]
            ].reset_index(drop=True)
            styled_div = (
                div_display.style
                .applymap(score_color, subset=["Financial Score", "Concall Score", "Combined Score"])
                .applymap(signal_color, subset=["Signal"])
            )
            st.dataframe(styled_div, use_container_width=True, hide_index=True,
                          height=min(len(div_display) * 40 + 45, 500))

        # ── Full comparison table ────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Full Comparison \u2014 All Companies (sorted by Combined Score)")
        full_display = both[
            ["Rank", "Company", "Financial Score", "Concall Score",
             "Combined Score", "Gap", "Stronger", "Signal"]
        ].reset_index(drop=True)
        styled_full = (
            full_display.style
            .applymap(score_color, subset=["Financial Score", "Concall Score", "Combined Score"])
            .applymap(signal_color, subset=["Signal"])
        )
        st.dataframe(styled_full, use_container_width=True, hide_index=True,
                      height=min(len(full_display) * 40 + 45, 700))

# ── Leaderboard ──────────────────────────────────────────────────────────────
with tab_leaderboard:
    if filtered.empty:
        st.info("No companies match the current filters.")
    else:
        st.subheader(f"Top {show_top_n} by {score_col}")

        top_display = filtered.head(show_top_n).reset_index(drop=True)
        score_cols_present = [c for c in ["Financial Score", "Concall Score", "Combined Score"] if c in top_display.columns]
        styled_lb = top_display[["Company"] + score_cols_present].style.applymap(
            score_color, subset=score_cols_present
        )
        st.dataframe(styled_lb, use_container_width=True, hide_index=True)

        # Inline file viewer
        st.markdown("---")
        st.subheader("View Analysis Files")
        company_list = top_display["Company"].tolist()
        selected_company = st.selectbox("Select a company", company_list, key="lb_file_viewer")

        _file_viewer_css = """
        <style>
        .file-viewer {
            background-color: #000000;
            color: #ffffff;
            font-family: 'Courier New', Courier, monospace;
            font-size: 13px;
            padding: 12px;
            border-radius: 6px;
            height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            line-height: 1.5;
        }
        </style>
        """
        st.markdown(_file_viewer_css, unsafe_allow_html=True)

        import html as _html
        col_fin, col_con, col_cred = st.columns(3)
        with col_fin:
            st.markdown("**Financial Analysis**")
            content = read_file_content(selected_company)
            if content:
                st.markdown(f'<div class="file-viewer">{_html.escape(content)}</div>', unsafe_allow_html=True)
            else:
                st.info("File not found")
        with col_con:
            st.markdown("**Concall (Walk the Talk)**")
            content = read_file_content(selected_company, "_concall")
            if content:
                st.markdown(f'<div class="file-viewer">{_html.escape(content)}</div>', unsafe_allow_html=True)
            else:
                st.info("File not found")
        with col_cred:
            st.markdown("**Credibility Score**")
            content = read_file_content(selected_company, "_concall_score")
            if content:
                st.markdown(f'<div class="file-viewer">{_html.escape(content)}</div>', unsafe_allow_html=True)
            else:
                st.info("File not found")

        # Companies missing one of the scores
        missing = df[df["Combined Score"].isna()]
        if not missing.empty:
            st.markdown("---")
            st.subheader("Companies Missing a Score")
            st.caption("These companies have only one of the two scores.")
            st.dataframe(
                missing[["Company", "Financial Score", "Concall Score"]].reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
            )

# ── Raw Data ─────────────────────────────────────────────────────────────────
with tab_data:
    st.subheader("Full Dataset")
    st.dataframe(df, use_container_width=True, height=600)

    col1, col2 = st.columns(2)
    with col1:
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Download as CSV",
            csv_bytes,
            file_name="individual_stock_scores.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col2:
        json_bytes = df.to_json(orient="records", indent=2).encode("utf-8")
        st.download_button(
            "Download as JSON",
            json_bytes,
            file_name="individual_stock_scores.json",
            mime="application/json",
            use_container_width=True,
        )
