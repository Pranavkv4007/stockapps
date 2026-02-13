"""
Sector Score Visualizer
Interactive Streamlit app to combine sector CSVs and visualize company scores.
"""

import os
import math
import glob
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ============================================================================
# Config
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SECTOR_DIR = os.path.join(PROJECT_ROOT, "Sector")
COMBINED_CSV = os.path.join(SECTOR_DIR, "Sector_Combined.csv")

st.set_page_config(
    page_title="Sector Score Visualizer",
    page_icon="\U0001F4CA",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# Data Loading — CsvCombiner logic
# ============================================================================


@st.cache_data
def run_csv_combiner():
    """Replicates CsvCombiner.ipynb: reads sector CSVs, filters top scores,
    combines into one dataframe, and saves (overwrites) Sector_Combined.csv."""
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
    # Always overwrite — never append
    final_df.to_csv(COMBINED_CSV, index=False, encoding="utf-8-sig")
    return final_df


@st.cache_data
def load_all_sectors():
    """Load ALL companies from every sector CSV (unfiltered) for full analysis."""
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


# ============================================================================
# Run combiner and load data
# ============================================================================

combined_df = run_csv_combiner()
all_df = load_all_sectors()

if combined_df.empty and all_df.empty:
    st.error("No sector CSV files found. Run the Full Sector Screener first to generate data.")
    st.stop()

# Use all_df as the primary dataset for full exploration
working_df = all_df if not all_df.empty else combined_df

# ============================================================================
# Sidebar — Filters (checkboxes for sectors + Select All)
# ============================================================================

with st.sidebar:
    st.title("\U0001F50D Filters")

    sectors = sorted(working_df["Sector"].dropna().unique())

    with st.expander("Sector Filter", expanded=False):
        # Select All toggle
        select_all = st.checkbox("Select All Sectors", value=True)

        selected_sectors = []
        for sector in sectors:
            checked = st.checkbox(sector, value=select_all, key=f"sector_{sector}")
            if checked:
                selected_sectors.append(sector)

    st.markdown("---")
    show_top_n = st.slider("Show Top N Sectors", min_value=1, max_value=max(len(sectors), 1), value=min(10, len(sectors)))

    st.markdown("---")
    if st.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption(
        f"Combined CSV: {len(combined_df)} top companies | "
        f"All data: {len(working_df)} companies across {len(sectors)} sectors"
    )

# Apply sector filter (score filtering only in Sector Analysis tab)
filtered_df = working_df[working_df["Sector"].isin(selected_sectors)].copy()
filtered_df = filtered_df.sort_values("score", ascending=False)

# ============================================================================
# Helper
# ============================================================================


def score_color(val):
    if val >= 80:
        return "background-color: #2d6a4f; color: white"
    elif val >= 60:
        return "background-color: #52b788; color: white"
    elif val >= 40:
        return "background-color: #f4a261; color: black"
    return "background-color: #e76f51; color: white"


# ============================================================================
# Header
# ============================================================================

st.title("Sector Score Visualizer")

# KPI row
k1, k2, k3, k4 = st.columns(4)
k1.metric("Sectors", len(filtered_df["Sector"].unique()))
k2.metric("Companies", len(filtered_df))
k3.metric("Avg Score", f"{filtered_df['score'].mean():.1f}" if not filtered_df.empty else "\u2014")
k4.metric("Top Score", int(filtered_df["score"].max()) if not filtered_df.empty else "\u2014")

st.markdown("---")

# ============================================================================
# Tabs
# ============================================================================

tab_overview, tab_sectors, tab_companies, tab_data = st.tabs(
    ["Overview", "Sector Analysis", "Company Leaderboard", "Raw Data"]
)

# ── Overview Tab ──────────────────────────────────────────────────────────────
with tab_overview:
    if filtered_df.empty:
        st.info("No sectors selected. Use the sidebar to select sectors.")
    else:
        # Sector summary table
        sector_summary = (
            filtered_df.groupby("Sector")["score"]
            .agg(
                Average_Score="mean",
                Top_Score="max",
                Companies_Analysed="count",
            )
            .reset_index()
            .sort_values("Top_Score", ascending=False)
        )
        sector_summary["Average_Score"] = sector_summary["Average_Score"].round(1)
        sector_summary = sector_summary.astype({"Top_Score": int, "Companies_Analysed": int})

        # Apply Top N filter — show top N sectors by highest top score
        sector_summary_top = sector_summary.head(show_top_n).reset_index(drop=True)

        st.subheader(f"Top {show_top_n} Sectors")
        styled_summary = sector_summary_top.style.applymap(
            score_color, subset=["Top_Score"]
        )
        st.dataframe(
            styled_summary,
            use_container_width=True,
            hide_index=True,
            height=min(len(sector_summary_top) * 40 + 40, 600),
        )

# ── Sector Analysis Tab ─────────────────────────────────────────────────────
with tab_sectors:
    if not selected_sectors:
        st.info("No sectors selected. Use the sidebar to select sectors.")
    else:
        selected_sector = st.selectbox("Drill into a Sector", options=selected_sectors)

        # Get full sector data (before score filtering)
        sector_data = filtered_df[filtered_df["Sector"] == selected_sector].sort_values(
            "score", ascending=False
        )

        if sector_data.empty:
            st.info("No companies found for this sector.")
        else:
            # Score slider — default to math.floor(max_score / 10) * 10
            sector_max = int(sector_data["score"].max())
            sector_min = int(sector_data["score"].min())
            default_floor = math.floor(sector_max / 10) * 10

            score_range = st.slider(
                "Filter by Score Range",
                min_value=sector_min,
                max_value=sector_max,
                value=(max(default_floor, sector_min), sector_max),
                key="sector_score_slider",
            )

            # Apply score filter for this tab only
            sector_data = sector_data[
                (sector_data["score"] >= score_range[0])
                & (sector_data["score"] <= score_range[1])
            ]

            if sector_data.empty:
                st.info("No companies match the selected score range.")
            else:
                s1, s2, s3 = st.columns(3)
                s1.metric("Companies", len(sector_data))
                s2.metric("Avg Score", f"{sector_data['score'].mean():.1f}")
                s3.metric("Top Score", int(sector_data["score"].max()))

                # Table display
                st.markdown("#### Company Scores")
                display_cols = ["company", "score"]
                if "url" in sector_data.columns:
                    display_cols.append("url")
                styled_table = (
                    sector_data[display_cols]
                    .reset_index(drop=True)
                    .style.applymap(score_color, subset=["score"])
                )
                st.dataframe(
                    styled_table,
                    use_container_width=True,
                    hide_index=True,
                    height=min(len(sector_data) * 40 + 40, 600),
                )

                # Horizontal bar chart for all companies in sector
                fig_sector = px.bar(
                    sector_data,
                    x="score",
                    y="company",
                    orientation="h",
                    color="score",
                    color_continuous_scale="RdYlGn",
                    title=f"{selected_sector} \u2014 Company Scores",
                    labels={"score": "Score", "company": ""},
                )
                fig_sector.update_layout(
                    height=max(len(sector_data) * 35, 300),
                    yaxis=dict(autorange="reversed"),
                    showlegend=False,
                )
                st.plotly_chart(fig_sector, use_container_width=True)

                # Score tier breakdown
                tier_labels = []
                for s in sector_data["score"]:
                    if s >= 80:
                        tier_labels.append("Excellent (80-100)")
                    elif s >= 60:
                        tier_labels.append("Good (60-79)")
                    elif s >= 40:
                        tier_labels.append("Average (40-59)")
                    else:
                        tier_labels.append("Below Average (<40)")
                sector_data = sector_data.copy()
                sector_data["Tier"] = tier_labels

                tier_counts = sector_data["Tier"].value_counts().reset_index()
                tier_counts.columns = ["Tier", "Count"]
                color_map = {
                    "Excellent (80-100)": "#2d6a4f",
                    "Good (60-79)": "#52b788",
                    "Average (40-59)": "#f4a261",
                    "Below Average (<40)": "#e76f51",
                }
                fig_pie = px.pie(
                    tier_counts,
                    values="Count",
                    names="Tier",
                    title="Score Tier Breakdown",
                    color="Tier",
                    color_discrete_map=color_map,
                )
                st.plotly_chart(fig_pie, use_container_width=True)

# ── Company Leaderboard Tab ──────────────────────────────────────────────────
with tab_companies:
    if filtered_df.empty:
        st.info("No sectors selected. Use the sidebar to select sectors.")
    else:
        # Top N per sector for leaderboard
        top_n_df = (
            filtered_df.groupby("Sector", group_keys=False)
            .apply(lambda g: g.nlargest(show_top_n, "score"))
            .reset_index(drop=True)
        )

        st.subheader(f"Top {show_top_n} Companies per Sector")

        # Overall leaderboard
        overall_top = filtered_df.nlargest(show_top_n, "score")

        st.markdown("#### Overall Top Companies")
        display_cols = ["company", "score", "Sector"]
        if "url" in overall_top.columns:
            display_cols.append("url")
        styled = overall_top[display_cols].reset_index(drop=True).style.applymap(
            score_color, subset=["score"]
        )
        st.dataframe(styled, use_container_width=True, height=min(len(overall_top) * 40 + 40, 600))

        st.markdown("---")
        st.markdown("#### Per-Sector Leaderboards")

        # Render per-sector leaderboards in two-column grid
        sector_list = sorted(top_n_df["Sector"].unique())
        for i in range(0, len(sector_list), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(sector_list):
                    break
                sector_name = sector_list[idx]
                sector_slice = top_n_df[top_n_df["Sector"] == sector_name][
                    ["company", "score"]
                ].reset_index(drop=True)
                with col:
                    st.markdown(f"**{sector_name}**")
                    styled_slice = sector_slice.style.applymap(score_color, subset=["score"])
                    st.dataframe(styled_slice, use_container_width=True, hide_index=True)

# ── Raw Data Tab ─────────────────────────────────────────────────────────────
with tab_data:
    st.subheader("Filtered Dataset")
    st.dataframe(filtered_df, use_container_width=True, height=600)

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        csv_filtered = filtered_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Download Filtered Data (CSV)",
            csv_filtered,
            file_name="filtered_sector_scores.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_dl2:
        if not combined_df.empty:
            csv_combined = combined_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Download Combined Top Scores (CSV)",
                csv_combined,
                file_name="Sector_Combined.csv",
                mime="text/csv",
                use_container_width=True,
            )
