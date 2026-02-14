"""
Stock Analysis Hub — FastAPI Entry Point
Serves both the REST API and the frontend static files.
"""

import os
import sys
import io
import zipfile
import json
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse

# Add project root to path so imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.routers import sector, individual, pipeline
from backend.config import SECTOR_DIR, INDIVIDUAL_DIR

app = FastAPI(
    title="Stock Analysis Hub",
    description="Unified stock analysis API combining sector screening and individual stock analysis.",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(sector.router)
app.include_router(individual.router)
app.include_router(pipeline.router)


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "sector_dir_exists": os.path.isdir(SECTOR_DIR),
        "individual_dir_exists": os.path.isdir(INDIVIDUAL_DIR),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/search")
def global_search(q: str = ""):
    """Search across both sectors and individual stocks by company name."""
    if not q or len(q) < 2:
        return {"sector_results": [], "individual_results": []}

    q_lower = q.lower()
    sector_results = []
    individual_results = []

    # Search sector data
    try:
        from backend.services.sector_service import load_all_sectors
        all_df = load_all_sectors()
        if not all_df.empty:
            matches = all_df[all_df["company"].str.lower().str.contains(q_lower, na=False)]
            sector_results = matches.head(20).to_dict(orient="records")
    except Exception:
        pass

    # Search individual data
    try:
        from backend.services.individual_service import load_individual_scores
        ind_df = load_individual_scores()
        if not ind_df.empty:
            matches = ind_df[ind_df["Company"].str.lower().str.contains(q_lower, na=False)]
            individual_results = matches.fillna("").head(20).to_dict(orient="records")
    except Exception:
        pass

    return {"sector_results": sector_results, "individual_results": individual_results}


@app.get("/api/cross-reference/{company_name}")
def cross_reference(company_name: str):
    """If a company appears in both sector and individual data, show combined profile."""
    result = {"company": company_name, "sector_data": None, "individual_data": None}

    try:
        from backend.services.sector_service import load_all_sectors
        all_df = load_all_sectors()
        if not all_df.empty:
            match = all_df[all_df["company"].str.lower() == company_name.lower()]
            if not match.empty:
                result["sector_data"] = match.iloc[0].to_dict()
    except Exception:
        pass

    try:
        from backend.services.individual_service import load_individual_scores
        ind_df = load_individual_scores()
        if not ind_df.empty:
            match = ind_df[ind_df["Company"].str.lower() == company_name.lower()]
            if not match.empty:
                result["individual_data"] = match.fillna("").iloc[0].to_dict()
    except Exception:
        pass

    return result


@app.get("/api/export-all")
def export_all():
    """Export all data (sectors + individual) as a ZIP file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        try:
            from backend.services.sector_service import load_all_sectors, run_csv_combiner
            all_df = load_all_sectors()
            if not all_df.empty:
                zf.writestr("sector_all_data.csv", all_df.to_csv(index=False))
            combined = run_csv_combiner()
            if not combined.empty:
                zf.writestr("sector_combined.csv", combined.to_csv(index=False))
        except Exception:
            pass

        try:
            from backend.services.individual_service import load_individual_scores
            ind_df = load_individual_scores()
            if not ind_df.empty:
                zf.writestr("individual_scores.csv", ind_df.to_csv(index=False))
                zf.writestr("individual_scores.json",
                            json.dumps(ind_df.fillna("").to_dict(orient="records"), indent=2))
        except Exception:
            pass

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=stock_analysis_hub_export.zip"},
    )


# Mount frontend static files LAST (catch-all)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
