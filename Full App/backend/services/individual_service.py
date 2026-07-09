"""
Individual stock data service — faithfully ported from Individualscoreapp.py.
Score extraction logic, signal classification, tier assignment.

CRITICAL: Regex patterns are copied EXACTLY from the original code.
Do NOT simplify or "improve" them.
"""

import os
import re
import json
import datetime
import pandas as pd
from backend.config import INDIVIDUAL_DIR, SCORES_JSON


# ============================================================================
# Score Extraction — EXACT copy from Individualscoreapp.py
# ============================================================================


def extract_overall_score(file_path: str) -> int | None:
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


def extract_credibility_score(file_path: str) -> float | None:
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
# Signal & Tier Classification — EXACT copy from originals
# ============================================================================


def assign_tier(score) -> str:
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


def assign_signal(fin, con) -> str:
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


# ============================================================================
# Data Loading
# ============================================================================


def load_individual_scores() -> pd.DataFrame:
    """Scan Individual_Stocks folder, extract both score types,
    save scores.json, and return a DataFrame."""

    if not os.path.isdir(INDIVIDUAL_DIR):
        return pd.DataFrame()

    overall_scores = {}
    credibility_scores = {}
    generated_dates = {}

    for filename in sorted(os.listdir(INDIVIDUAL_DIR)):
        filepath = os.path.join(INDIVIDUAL_DIR, filename)

        # Overall score files: *.txt without underscores in the name
        if filename.endswith(".txt") and "_" not in filename.replace(".txt", ""):
            company = filename.replace(".txt", "")
            score = extract_overall_score(filepath)
            if score is not None:
                overall_scores[company] = score
            generated_dates[company] = datetime.date.fromtimestamp(
                os.path.getmtime(filepath)
            ).isoformat()

        # Credibility score files: *_concall_score.txt
        elif filename.endswith("_concall_score.txt"):
            company = filename.replace("_concall_score.txt", "")
            score = extract_credibility_score(filepath)
            if score is not None:
                credibility_scores[company] = score

    # Save scores.json
    results = {
        "overall_scores": overall_scores,
        "credibility_scores": credibility_scores,
    }
    try:
        with open(SCORES_JSON, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
    except Exception:
        pass

    # Merge into a single DataFrame
    all_companies = sorted(set(overall_scores.keys()) | set(credibility_scores.keys()))
    records = []
    for company in all_companies:
        overall = overall_scores.get(company)
        credibility = credibility_scores.get(company)
        combined = None
        if overall is not None and credibility is not None:
            combined = round((overall + credibility) / 2, 1)
        records.append({
            "Company": company,
            "Financial Score": overall,
            "Concall Score": credibility,
            "Combined Score": combined,
            "Tier": assign_tier(combined if combined is not None else (overall or credibility)),
            "Signal": assign_signal(overall, credibility),
            "Generated": generated_dates.get(company),
        })

    return pd.DataFrame(records)


def get_comparison_data(df: pd.DataFrame) -> list[dict]:
    """Returns companies with BOTH scores, including gap analysis."""
    if df.empty:
        return []
    both = df.dropna(subset=["Financial Score", "Concall Score"]).copy()
    if both.empty:
        return []
    both["Gap"] = (both["Financial Score"] - both["Concall Score"]).round(1)
    both["Abs Gap"] = both["Gap"].abs()
    both["Stronger"] = both["Gap"].apply(
        lambda g: "Financials" if g > 5 else ("Concall" if g < -5 else "Balanced")
    )
    both = both.sort_values("Combined Score", ascending=False)
    return both.to_dict(orient="records")


def get_aligned(df: pd.DataFrame) -> list[dict]:
    """Companies where |gap| <= 10."""
    both = df.dropna(subset=["Financial Score", "Concall Score"]).copy()
    if both.empty:
        return []
    both["Gap"] = (both["Financial Score"] - both["Concall Score"]).round(1)
    both["Abs Gap"] = both["Gap"].abs()
    aligned = both[both["Abs Gap"] <= 10].sort_values("Combined Score", ascending=False)
    return aligned.to_dict(orient="records")


def get_divergent(df: pd.DataFrame) -> list[dict]:
    """Companies where |gap| > 10."""
    both = df.dropna(subset=["Financial Score", "Concall Score"]).copy()
    if both.empty:
        return []
    both["Gap"] = (both["Financial Score"] - both["Concall Score"]).round(1)
    both["Abs Gap"] = both["Gap"].abs()
    both["Stronger"] = both["Gap"].apply(
        lambda g: "Financials" if g > 5 else ("Concall" if g < -5 else "Balanced")
    )
    divergent = both[both["Abs Gap"] > 10].sort_values("Abs Gap", ascending=False)
    return divergent.to_dict(orient="records")


def get_missing(df: pd.DataFrame) -> list[dict]:
    """Companies missing one or both scores."""
    if df.empty:
        return []
    missing = df[df["Combined Score"].isna()]
    return missing.to_dict(orient="records")


def get_tier_summary(df: pd.DataFrame) -> dict:
    """Count of companies per tier."""
    if df.empty:
        return {}
    # Use Combined Score where available, else Financial, else Concall
    scores = df.apply(
        lambda r: r["Combined Score"] if pd.notna(r["Combined Score"])
        else (r["Financial Score"] if pd.notna(r["Financial Score"]) else r["Concall Score"]),
        axis=1,
    )
    tiers = scores.apply(assign_tier)
    counts = tiers.value_counts().to_dict()
    return {
        "Excellent": counts.get("Excellent", 0),
        "Good": counts.get("Good", 0),
        "Average": counts.get("Average", 0),
        "Weak": counts.get("Weak", 0),
    }


def get_data_freshness() -> dict:
    """Return last modified timestamps of individual stock files."""
    result = {}
    if os.path.isdir(INDIVIDUAL_DIR):
        for filename in os.listdir(INDIVIDUAL_DIR):
            if filename.endswith(".txt"):
                filepath = os.path.join(INDIVIDUAL_DIR, filename)
                result[filename] = os.path.getmtime(filepath)
    return result
