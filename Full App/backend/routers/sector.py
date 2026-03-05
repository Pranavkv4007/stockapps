"""
Sector API endpoints — /api/sector/*
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import pandas as pd
import os
import io
import shutil

from backend.services.sector_service import (
    run_csv_combiner,
    load_all_sectors,
    get_sector_summary,
    get_sector_data,
    get_data_freshness,
)
from backend.config import SECTOR_DIR

router = APIRouter(prefix="/api/sector", tags=["sector"])

# Cache dataframes with staleness detection
_combined_df: pd.DataFrame | None = None
_all_df: pd.DataFrame | None = None
_last_mtime: float = 0.0


def _get_dir_mtime() -> float:
    """Get the latest modification time of any CSV file in the Sector directory tree."""
    latest = 0.0
    if os.path.isdir(SECTOR_DIR):
        for root, _dirs, files in os.walk(SECTOR_DIR):
            for f in files:
                if f.endswith(".csv"):
                    t = os.path.getmtime(os.path.join(root, f))
                    if t > latest:
                        latest = t
    return latest


def _ensure_loaded():
    global _combined_df, _all_df, _last_mtime
    current_mtime = _get_dir_mtime()
    if _combined_df is None or current_mtime > _last_mtime:
        _combined_df = run_csv_combiner()
        _all_df = load_all_sectors()
        _last_mtime = current_mtime


def _refresh():
    global _combined_df, _all_df, _last_mtime
    _combined_df = run_csv_combiner()
    _all_df = load_all_sectors()
    _last_mtime = _get_dir_mtime()


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


# ── File Manager endpoints ────────────────────────────────────────────────────

def _scan_sector_folder(sector_name: str) -> dict | None:
    """Scan a single sector folder and return file presence info."""
    sector_path = os.path.join(SECTOR_DIR, sector_name)
    if not os.path.isdir(sector_path):
        return None
    info: dict = {"companies": {}, "csv": False, "json": False, "progress": False}
    for filename in sorted(os.listdir(sector_path)):
        filepath = os.path.join(sector_path, filename)
        if not os.path.isfile(filepath):
            continue
        if filename == "progress.json":
            info["progress"] = True
        elif filename.endswith(".csv"):
            info["csv"] = True
        elif filename.endswith(".json"):
            info["json"] = True
        elif filename.endswith("_Score.txt"):
            company = filename[: -len("_Score.txt")]
            info["companies"].setdefault(company, {"main": False, "score": False})
            info["companies"][company]["score"] = True
        elif filename.endswith(".txt"):
            company = filename[: -len(".txt")]
            info["companies"].setdefault(company, {"main": False, "score": False})
            info["companies"][company]["main"] = True
    return info


@router.get("/files")
def get_files():
    """List all sector folders with file presence info."""
    if not os.path.isdir(SECTOR_DIR):
        return {"sectors": {}}
    sectors = {}
    for sector_name in sorted(os.listdir(SECTOR_DIR)):
        info = _scan_sector_folder(sector_name)
        if info is not None:
            sectors[sector_name] = info
    return {"sectors": sectors}


@router.delete("/files/{sector_name}")
def delete_sector_files(sector_name: str, types: str = Query("")):
    """Delete sector-level files (types: csv, json, progress)."""
    sector_path = os.path.join(SECTOR_DIR, sector_name)
    if not os.path.isdir(sector_path):
        raise HTTPException(status_code=404, detail="Sector not found")
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    deleted, errors = [], []
    for filename in os.listdir(sector_path):
        filepath = os.path.join(sector_path, filename)
        if not os.path.isfile(filepath):
            continue
        if "csv" in type_list and filename.endswith(".csv"):
            try:
                os.remove(filepath)
                deleted.append(filename)
            except Exception as e:
                errors.append(str(e))
        elif "json" in type_list and filename.endswith(".json") and filename != "progress.json":
            try:
                os.remove(filepath)
                deleted.append(filename)
            except Exception as e:
                errors.append(str(e))
        elif "progress" in type_list and filename == "progress.json":
            try:
                os.remove(filepath)
                deleted.append(filename)
            except Exception as e:
                errors.append(str(e))
    _refresh()
    return {"deleted": deleted, "errors": errors}


@router.delete("/folder/{sector_name}")
def delete_sector_folder(sector_name: str, confirm: str = Query("")):
    """Delete entire sector folder. Requires confirm=sector_name."""
    if confirm != sector_name:
        raise HTTPException(status_code=400, detail="Confirmation name does not match")
    sector_path = os.path.join(SECTOR_DIR, sector_name)
    if not os.path.isdir(sector_path):
        raise HTTPException(status_code=404, detail="Sector not found")
    try:
        shutil.rmtree(sector_path)
        _refresh()
        return {"deleted": sector_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/company/{sector_name}/{company}")
def delete_company_files(sector_name: str, company: str, types: str = Query("")):
    """Delete company files within a sector (types: main, score)."""
    sector_path = os.path.join(SECTOR_DIR, sector_name)
    if not os.path.isdir(sector_path):
        raise HTTPException(status_code=404, detail="Sector not found")
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    file_map = {
        "main": os.path.join(sector_path, f"{company}.txt"),
        "score": os.path.join(sector_path, f"{company}_Score.txt"),
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
