"""
Sector API endpoints — /api/sector/*
"""

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
import pandas as pd
import io

from backend.services.sector_service import (
    run_csv_combiner,
    load_all_sectors,
    get_sector_summary,
    get_sector_data,
    get_data_freshness,
)

router = APIRouter(prefix="/api/sector", tags=["sector"])

# Cache dataframes in module-level variables (refreshable)
_combined_df: pd.DataFrame | None = None
_all_df: pd.DataFrame | None = None


def _ensure_loaded():
    global _combined_df, _all_df
    if _combined_df is None:
        _combined_df = run_csv_combiner()
    if _all_df is None:
        _all_df = load_all_sectors()


def _refresh():
    global _combined_df, _all_df
    _combined_df = run_csv_combiner()
    _all_df = load_all_sectors()


def _clean_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of dicts with NaN replaced by null-safe values."""
    import json as _json
    return _json.loads(df.to_json(orient="records"))


@router.get("/combined")
def get_combined():
    """Returns the filtered top-score companies (replicating run_csv_combiner logic)."""
    _ensure_loaded()
    if _combined_df is None or _combined_df.empty:
        return {"data": [], "count": 0, "error": "No sector data found. Ensure Sector directory exists with CSV files."}
    df = _combined_df.sort_values("score", ascending=False)
    return {"data": _clean_records(df), "count": len(df)}


@router.get("/all")
def get_all():
    """Returns ALL companies from all sector CSVs (unfiltered)."""
    _ensure_loaded()
    if _all_df is None or _all_df.empty:
        return {"data": [], "count": 0}
    df = _all_df.sort_values("score", ascending=False)
    return {"data": _clean_records(df), "count": len(df)}


@router.get("/summary")
def get_summary(top_n: int = Query(10, ge=1)):
    """Aggregated stats per sector."""
    _ensure_loaded()
    if _all_df is None or _all_df.empty:
        return {"data": []}
    return {"data": get_sector_summary(_all_df, top_n)}


@router.get("/sectors")
def list_sectors():
    """List all available sector names."""
    _ensure_loaded()
    if _all_df is None or _all_df.empty:
        return {"sectors": []}
    sectors = sorted(_all_df["Sector"].dropna().unique().tolist())
    return {"sectors": sectors}


@router.get("/detail/{sector_name}")
def get_sector_detail(sector_name: str,
                      min_score: float = Query(0, ge=0),
                      max_score: float = Query(100, le=100)):
    """All companies in a specific sector."""
    _ensure_loaded()
    if _all_df is None or _all_df.empty:
        return {"data": []}
    return {"data": get_sector_data(_all_df, sector_name, min_score, max_score)}


@router.get("/download/filtered")
def download_filtered():
    """CSV download of filtered (combined top scores) data."""
    _ensure_loaded()
    if _combined_df is None or _combined_df.empty:
        return {"error": "No data available"}
    buf = io.StringIO()
    _combined_df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=filtered_sector_scores.csv"},
    )


@router.get("/download/combined")
def download_combined():
    """CSV download of combined top scores."""
    _ensure_loaded()
    if _combined_df is None or _combined_df.empty:
        return {"error": "No data available"}
    buf = io.StringIO()
    _combined_df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Sector_Combined.csv"},
    )


@router.get("/freshness")
def freshness():
    """Data freshness indicator."""
    return {"files": get_data_freshness()}


@router.post("/refresh")
def refresh():
    """Refresh cached data."""
    _refresh()
    return {"status": "refreshed"}
