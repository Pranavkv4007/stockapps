"""
Individual Stock API endpoints — /api/individual/*
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import pandas as pd
import os
import io
import json
import datetime

from backend.services.individual_service import (
    load_individual_scores,
    get_comparison_data,
    get_aligned,
    get_divergent,
    get_missing,
    get_tier_summary,
    get_data_freshness,
)
from backend.config import INDIVIDUAL_DIR

router = APIRouter(prefix="/api/individual", tags=["individual"])

# Module-level cache with staleness detection
_df: pd.DataFrame | None = None
_last_mtime: float = 0.0


def _get_dir_mtime() -> float:
    """Get the latest modification time of any .txt file in Individual_Stocks."""
    latest = 0.0
    if os.path.isdir(INDIVIDUAL_DIR):
        for f in os.listdir(INDIVIDUAL_DIR):
            if f.endswith(".txt"):
                t = os.path.getmtime(os.path.join(INDIVIDUAL_DIR, f))
                if t > latest:
                    latest = t
    return latest


def _ensure_loaded():
    global _df, _last_mtime
    current_mtime = _get_dir_mtime()
    if _df is None or current_mtime > _last_mtime:
        _df = load_individual_scores()
        _last_mtime = current_mtime


def _refresh():
    global _df, _last_mtime
    _df = load_individual_scores()
    _last_mtime = _get_dir_mtime()


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


# ── File Manager endpoints ────────────────────────────────────────────────────

def _scan_individual_files() -> dict:
    """Scan Individual_Stocks dir and return file presence + generation dates per company."""
    if not os.path.isdir(INDIVIDUAL_DIR):
        return {}
    companies: dict = {}
    for filename in sorted(os.listdir(INDIVIDUAL_DIR)):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(INDIVIDUAL_DIR, filename)
        mtime = datetime.date.fromtimestamp(os.path.getmtime(filepath)).isoformat()
        if filename.endswith("_concall_score.txt"):
            company = filename[: -len("_concall_score.txt")]
            key, date_key = "concall_score", "concall_score_date"
        elif filename.endswith("_concall.txt"):
            company = filename[: -len("_concall.txt")]
            key, date_key = "concall", "concall_date"
        else:
            company = filename[: -len(".txt")]
            key, date_key = "main", "main_date"
        companies.setdefault(company, {
            "main": False, "concall": False, "concall_score": False,
            "main_date": None, "concall_date": None, "concall_score_date": None,
        })
        companies[company][key] = True
        companies[company][date_key] = mtime
    return companies


@router.get("/files")
def get_files():
    """List all individual stock files with presence info per company."""
    return {"companies": _scan_individual_files()}


@router.delete("/files/{company}")
def delete_individual_files(company: str, types: str = Query("")):
    """Delete specific file types for a company (types: main, concall, concall_score)."""
    if not os.path.isdir(INDIVIDUAL_DIR):
        raise HTTPException(status_code=404, detail="Individual_Stocks directory not found")
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    file_map = {
        "main": os.path.join(INDIVIDUAL_DIR, f"{company}.txt"),
        "concall": os.path.join(INDIVIDUAL_DIR, f"{company}_concall.txt"),
        "concall_score": os.path.join(INDIVIDUAL_DIR, f"{company}_concall_score.txt"),
    }
    deleted, errors = [], []
    for t in type_list:
        if t in file_map and os.path.exists(file_map[t]):
            try:
                os.remove(file_map[t])
                deleted.append(os.path.basename(file_map[t]))
            except Exception as e:
                errors.append(str(e))
    _refresh()
    return {"deleted": deleted, "errors": errors}
