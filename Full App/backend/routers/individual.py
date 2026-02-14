"""
Individual Stock API endpoints — /api/individual/*
"""

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
import pandas as pd
import io
import json

from backend.services.individual_service import (
    load_individual_scores,
    get_comparison_data,
    get_aligned,
    get_divergent,
    get_missing,
    get_tier_summary,
    get_data_freshness,
)

router = APIRouter(prefix="/api/individual", tags=["individual"])

# Module-level cache
_df: pd.DataFrame | None = None


def _ensure_loaded():
    global _df
    if _df is None:
        _df = load_individual_scores()


def _refresh():
    global _df
    _df = load_individual_scores()


@router.get("/scores")
def get_scores(sort_by: str = Query("Combined Score"),
               min_score: float = Query(0, ge=0),
               max_score: float = Query(100, le=100)):
    """Returns all individual stock scores."""
    _ensure_loaded()
    if _df is None or _df.empty:
        return {"data": [], "count": 0, "error": "No individual stock data found. Ensure Individual_Stocks directory exists."}

    df = _df.copy()
    # Filter by score range on the chosen column if it exists
    if sort_by in df.columns:
        valid = df[df[sort_by].notna()]
        valid = valid[(valid[sort_by] >= min_score) & (valid[sort_by] <= max_score)]
        valid = valid.sort_values(sort_by, ascending=False)
    else:
        valid = df
    return {"data": valid.fillna("").to_dict(orient="records"), "count": len(valid)}


@router.get("/comparison")
def get_comparison():
    """Returns companies with BOTH scores, including gap analysis."""
    _ensure_loaded()
    if _df is None or _df.empty:
        return {"data": []}
    return {"data": get_comparison_data(_df)}


@router.get("/aligned")
def get_aligned_stocks():
    """Companies where |gap| <= 10."""
    _ensure_loaded()
    if _df is None or _df.empty:
        return {"data": []}
    return {"data": get_aligned(_df)}


@router.get("/divergent")
def get_divergent_stocks():
    """Companies where |gap| > 10."""
    _ensure_loaded()
    if _df is None or _df.empty:
        return {"data": []}
    return {"data": get_divergent(_df)}


@router.get("/missing")
def get_missing_scores():
    """Companies missing one or both scores."""
    _ensure_loaded()
    if _df is None or _df.empty:
        return {"data": []}
    return {"data": get_missing(_df)}


@router.get("/tier-summary")
def tier_summary():
    """Count of companies per tier."""
    _ensure_loaded()
    if _df is None or _df.empty:
        return {"data": {}}
    return {"data": get_tier_summary(_df)}


@router.get("/download/csv")
def download_csv():
    """CSV download."""
    _ensure_loaded()
    if _df is None or _df.empty:
        return {"error": "No data available"}
    buf = io.StringIO()
    _df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=individual_stock_scores.csv"},
    )


@router.get("/download/json")
def download_json():
    """JSON download."""
    _ensure_loaded()
    if _df is None or _df.empty:
        return {"error": "No data available"}
    data = _df.fillna("").to_dict(orient="records")
    content = json.dumps(data, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=individual_stock_scores.json"},
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
