"""
Sector data service — faithfully ported from ScoreVisualApp.py.
CSV combiner logic, sector aggregation, filtering.
"""

import os
import math
import glob
import pandas as pd
from backend.config import SECTOR_DIR, COMBINED_CSV


def run_csv_combiner() -> pd.DataFrame:
    """Replicates CsvCombiner logic: reads sector CSVs, filters top scores,
    combines into one dataframe, and saves Sector_Combined.csv."""
    df_list = []

    if not os.path.isdir(SECTOR_DIR):
        return pd.DataFrame()

    for item in os.listdir(SECTOR_DIR):
        full_path = os.path.join(SECTOR_DIR, item)
        if not os.path.isdir(full_path):
            continue
        for file in glob.glob(os.path.join(full_path, "*.csv")):
            try:
                df = pd.read_csv(file)
                if "score" not in df.columns:
                    continue
                df_sorted = df.sort_values(by="score", ascending=False)
                max_score = math.floor(df_sorted["score"].iloc[0] / 10) * 10
                df_filtered = df_sorted[df_sorted["score"] >= max_score]
                df_list.append(df_filtered)
            except Exception:
                continue

    if not df_list:
        return pd.DataFrame()

    final_df = pd.concat(df_list, ignore_index=True)
    try:
        final_df.to_csv(COMBINED_CSV, index=False, encoding="utf-8-sig")
    except Exception:
        pass
    return final_df


def load_all_sectors() -> pd.DataFrame:
    """Load ALL companies from every sector CSV (unfiltered)."""
    df_list = []
    if not os.path.isdir(SECTOR_DIR):
        return pd.DataFrame()
    for item in os.listdir(SECTOR_DIR):
        full_path = os.path.join(SECTOR_DIR, item)
        if not os.path.isdir(full_path):
            continue
        for file in glob.glob(os.path.join(full_path, "*.csv")):
            try:
                df = pd.read_csv(file)
                if "score" not in df.columns:
                    continue
                df_list.append(df)
            except Exception:
                continue
    if not df_list:
        return pd.DataFrame()
    return pd.concat(df_list, ignore_index=True)


def get_sector_summary(df: pd.DataFrame, top_n: int = 10) -> list[dict]:
    """Aggregated stats per sector: avg_score, top_score, company_count."""
    if df.empty:
        return []
    summary = (
        df.groupby("Sector")["score"]
        .agg(
            avg_score="mean",
            top_score="max",
            company_count="count",
        )
        .reset_index()
        .sort_values("top_score", ascending=False)
    )
    summary["avg_score"] = summary["avg_score"].round(1)
    summary["top_score"] = summary["top_score"].astype(int)
    summary["company_count"] = summary["company_count"].astype(int)
    import json as _json
    return _json.loads(summary.head(top_n).to_json(orient="records"))


def get_sector_data(df: pd.DataFrame, sector_name: str,
                    min_score: float = 0, max_score: float = 100) -> list[dict]:
    """All companies in a specific sector, filtered by score range."""
    if df.empty:
        return []
    sector_df = df[df["Sector"] == sector_name].copy()
    sector_df = sector_df[
        (sector_df["score"] >= min_score) & (sector_df["score"] <= max_score)
    ].sort_values("score", ascending=False)
    import json as _json
    return _json.loads(sector_df.to_json(orient="records"))


def get_data_freshness() -> dict:
    """Return last modified timestamps of source files."""
    result = {}
    if os.path.isdir(SECTOR_DIR):
        for item in os.listdir(SECTOR_DIR):
            full_path = os.path.join(SECTOR_DIR, item)
            if os.path.isdir(full_path):
                for file in glob.glob(os.path.join(full_path, "*.csv")):
                    mtime = os.path.getmtime(file)
                    result[os.path.basename(file)] = mtime
    return result
