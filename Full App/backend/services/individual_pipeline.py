"""
8-step individual stock pipeline — exact port from IndividualStockApp.py.
Runs asynchronously, pushes SSE events via PipelineManager.
"""

import os
import time
import asyncio

from backend.config import SECTOR_DIR, INDIVIDUAL_DIR
from backend.services.pipeline_manager import PipelineManager
from backend.services.llm_service import (
    llm, gemini_llm_kpi, clean_and_parse_json, clean_text_for_llm,
    resolve_gemini_model_id,
)
from backend.services.scraper_service import Website, get_subsector_details, get_sector_names
from backend.services import prompts

mgr = PipelineManager()

os.makedirs(INDIVIDUAL_DIR, exist_ok=True)

# Step dependency map: step_index -> list of result keys that must be non-None
STEP_DEPS = {
    0: [],  # no deps
    1: ["site_text"],
    2: ["result_financial_text"],
    3: ["result_financial_json"],
    4: ["result_kpi_json"],
    5: ["result_kpi_values_clean"],
    6: ["company_name"],
    7: ["result_walkthetalk"],
}

STEP_LABELS = [
    "Scrape & Extract Metadata",
    "Financial Data Extraction",
    "JSON Conversion",
    "Sector KPI Generation",
    "KPI Value Extraction",
    "Final Comprehensive Analysis",
    "Walk the Talk Analysis",
    "Concall Credibility Score",
]


async def run_individual_pipeline(
    run_id: str,
    url: str,
    models: dict = None,
    custom_prompts: dict = None,
    step_only: int = None,
):
    """
    Execute individual stock pipeline.
    If step_only is set, run only that step (step-by-step mode).
    Otherwise run all 8 steps sequentially.
    """
    run = mgr.get_run(run_id)
    if not run:
        return

    models = models or {}
    custom_prompts = custom_prompts or {}

    # Model selections per step
    m1 = models.get("step1", "gemini-flash")
    m2 = models.get("step2", "gemini-flash-lite")
    m3 = models.get("step3", "gemini-flash")
    m4 = models.get("step4", "gemini-flash")
    m5 = models.get("step5", "gemini-pro")
    m6 = models.get("step6", "gemini-pro")
    m7 = models.get("step7", "gemini-flash")

    # Custom prompts with defaults
    sp_screener = custom_prompts.get("screener", prompts.DEFAULT_SYSTEM_PROMPT_SCREENER_IND)
    sp_json = custom_prompts.get("json", prompts.DEFAULT_SYSTEM_PROMPT_JSON_IND)
    sp_kpi = custom_prompts.get("kpi", prompts.DEFAULT_SYSTEM_PROMPT_KPI)
    sp_kpi_cal = custom_prompts.get("kpi_cal", prompts.DEFAULT_SYSTEM_PROMPT_KPI_CAL)
    sp_gemini_search = custom_prompts.get("gemini_search", prompts.DEFAULT_SYSTEM_PROMPT_GEMINI_SEARCH)
    sp_final = custom_prompts.get("final", prompts.DEFAULT_SYSTEM_PROMPT_FINAL)
    sp_concall_score = custom_prompts.get("concall_score", prompts.DEFAULT_SYSTEM_PROMPT_CONCALL_SCORE)

    run.status = "running"
    log = lambda msg: mgr.add_log(run_id, msg)
    event = lambda t, d: mgr.push_event(run_id, t, d)

    # Intermediate state stored in run.results
    r = run.results
    r.setdefault("company_name", "")
    r.setdefault("sector_name", "")
    r.setdefault("sub_sector", "")
    r.setdefault("site_text", "")
    r.setdefault("result_financial_text", None)
    r.setdefault("result_financial_json", None)
    r.setdefault("result_kpi_json", None)
    r.setdefault("result_kpi_values", None)
    r.setdefault("result_kpi_values_clean", None)
    r.setdefault("result_final_analysis", None)
    r.setdefault("result_walkthetalk", None)
    r.setdefault("concall_source", "llm_synthesis")
    r.setdefault("result_concall_score", None)

    steps_to_run = [step_only] if step_only is not None else list(range(8))

    try:
        for step_idx in steps_to_run:
            if run.is_cancelled():
                return

            run.phase = step_idx
            label = STEP_LABELS[step_idx]
            event("phase_start", {"phase": step_idx, "label": f"Step {step_idx}: {label}"})
            log(f"Step {step_idx}: {label}...")

            # Check dependencies
            deps = STEP_DEPS[step_idx]
            missing = [d for d in deps if not r.get(d)]
            if missing:
                msg = f"Step {step_idx} requires: {', '.join(missing)}. Run previous steps first."
                log(f"ERROR: {msg}")
                event("error", {"message": msg})
                run.status = "failed"
                run.error = msg
                return

            success = False

            if step_idx == 0:
                success = await _step_0(run_id, url, r, log)
            elif step_idx == 1:
                success = await _step_1(run_id, r, log, sp_screener, m1)
            elif step_idx == 2:
                success = await _step_2(run_id, r, log, sp_json, m2)
            elif step_idx == 3:
                success = await _step_3(run_id, r, log, sp_kpi, m3)
            elif step_idx == 4:
                success = await _step_4(run_id, r, log, sp_gemini_search, sp_kpi_cal, m4)
            elif step_idx == 5:
                success = await _step_5(run_id, r, log, sp_final, m5)
            elif step_idx == 6:
                success = await _step_6(run_id, r, log, m6)
            elif step_idx == 7:
                success = await _step_7(run_id, r, log, sp_concall_score, m7)

            if not success:
                run.status = "failed"
                run.error = f"Step {step_idx} failed"
                event("error", {"message": f"Step {step_idx} failed"})
                return

            run.progress = (step_idx + 1) / 8
            run.progress_text = f"Step {step_idx} complete"
            event("phase_complete", {"phase": step_idx})

            # ── Cache check after step 0 (full run only) ──
            if step_idx == 0 and step_only is None:
                company_name = r["company_name"]
                sub_sector = r["sub_sector"]
                existing_files = []

                sector_cache = os.path.join(SECTOR_DIR, sub_sector, company_name + ".txt")
                if os.path.exists(sector_cache):
                    existing_files.append(f"{sub_sector}/{company_name}.txt")

                for suffix in [".txt", "_concall.txt", "_concall_score.txt"]:
                    fp = os.path.join(INDIVIDUAL_DIR, company_name + suffix)
                    if os.path.exists(fp):
                        existing_files.append(f"Individual_Stocks/{company_name}{suffix}")

                if existing_files:
                    run.status = "awaiting_cache_decision"
                    log(f"Cache check: {len(existing_files)} existing file(s) found. Waiting for your decision...")
                    event("cache_prompt", {"files": existing_files, "count": len(existing_files), "company": company_name})
                    await run._cache_event.wait()

                    if run.is_cancelled():
                        return

                    if run.cache_decision == "delete":
                        if os.path.exists(sector_cache):
                            try:
                                os.remove(sector_cache)
                            except Exception:
                                pass
                        for suffix in [".txt", "_concall.txt", "_concall_score.txt"]:
                            fp = os.path.join(INDIVIDUAL_DIR, company_name + suffix)
                            if os.path.exists(fp):
                                try:
                                    os.remove(fp)
                                except Exception:
                                    pass
                        log("Cache deleted. Starting fresh run.")
                    else:
                        log("Continuing with cached files.")

        run.status = "completed"
        run.progress = 1.0
        run.progress_text = "Pipeline completed!"
        log("Pipeline finished.")
        event("done", {"message": "Pipeline completed!"})

    except Exception as e:
        run.status = "failed"
        run.error = str(e)
        log(f"PIPELINE ERROR: {e}")
        event("error", {"message": str(e)})


async def _step_0(run_id, url, r, log):
    """Scrape URL, extract company name/sector/sub-sector."""
    if not url:
        log("ERROR: No URL provided.")
        return False

    site = await asyncio.to_thread(Website, url)
    r["site_text"] = site.get_financial_text()
    r["company_name"] = site.get_company_name()
    log(f"Company: {r['company_name']}")

    try:
        # Pass the already-fetched site object to avoid a redundant HTTP request
        links = await asyncio.to_thread(get_subsector_details, site)
        sector_name, sub_sector = await asyncio.to_thread(get_sector_names, links)
        r["sector_name"] = sector_name
        r["sub_sector"] = sub_sector
        log(f"Sector: {sector_name}, Sub-sector: {sub_sector}")
    except Exception as e:
        log(f"WARNING: Could not extract sector info: {e}")
        r["sector_name"] = "Unknown"
        r["sub_sector"] = "Unknown"
    return True


async def _step_1(run_id, r, log, sp_screener, model):
    """Financial data extraction (checks cache first)."""
    company_name = r["company_name"]
    sub_sector = r["sub_sector"]

    sector_path = os.path.join(SECTOR_DIR, sub_sector)
    file_name = company_name + ".txt"
    full_path = os.path.join(sector_path, file_name)

    if os.path.exists(full_path):
        log(f"Found cached data at: {full_path}")
        with open(full_path, "r", encoding="utf-8") as f:
            response = f.read()
    else:
        log(f"No cache. Calling LLM ({model})...")
        up = prompts.user_prompt_screener_ind(r["site_text"])
        response = await asyncio.to_thread(llm, sp_screener, up, model)
        os.makedirs(sector_path, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(response)
        log(f"Saved to cache: {full_path}")

    r["result_financial_text"] = response
    return True


async def _step_2(run_id, r, log, sp_json, model):
    """Convert to structured JSON."""
    log(f"Converting to JSON ({model})...")
    result = await asyncio.to_thread(
        llm, sp_json, prompts.create_user_json(r["result_financial_text"]), model
    )
    parsed = clean_and_parse_json(result)
    if parsed is None:
        log("WARNING: JSON parsing failed. Storing raw text.")
        r["result_financial_json"] = result
    else:
        r["result_financial_json"] = parsed
        log("JSON parsed successfully.")
    return True


async def _step_3(run_id, r, log, sp_kpi, model):
    """Generate sector-specific KPIs."""
    log(f"Generating sector KPIs ({model})...")
    up = prompts.user_prompts_kpi(r["sector_name"], r["sub_sector"])
    result = await asyncio.to_thread(llm, sp_kpi, up, model)
    r["result_kpi_json"] = result
    return True


async def _step_4(run_id, r, log, sp_gemini_search, sp_kpi_cal, model):
    """Extract KPI values via Gemini Search (fallback to calculation)."""
    company_name = r["company_name"]
    kpi_json = r["result_kpi_json"]

    try:
        log("Trying Gemini Search for KPI values...")
        up = prompts.user_prompts_gemini_search(company_name, kpi_json)
        sector_kpis_ratios = await asyncio.to_thread(
            gemini_llm_kpi, sp_gemini_search, up, company_name
        )
        log("Gemini Search successful.")
    except Exception as e:
        log(f"Gemini Search failed: {e}. Falling back to calculation...")
        up = prompts.user_prompts_kpi_cal(r["result_financial_json"], kpi_json)
        sector_kpis_ratios = await asyncio.to_thread(llm, sp_kpi_cal, up, model)

    r["result_kpi_values"] = sector_kpis_ratios

    # Clean KPI output
    log("Cleaning KPI output...")
    clean_system = (
        "You are a precise financial data extractor. "
        "Read the provided financial summary and output only the numerical values with their field names. "
        "Exclude all fields with N/A, missing values, or descriptive wording. "
        "Return the result strictly in JSON format with key-value pairs."
    )
    clean_user = f"The following is the financial data: {sector_kpis_ratios}"
    r["result_kpi_values_clean"] = await asyncio.to_thread(
        llm, clean_system, clean_user, model
    )
    return True


async def _step_5(run_id, r, log, sp_final, model):
    """Final comprehensive analysis."""
    log(f"Final analysis ({model})...")
    up = prompts.create_user_prompt_final(
        r["company_name"], r["sector_name"], r["sub_sector"],
        r["result_financial_json"], r["result_kpi_values_clean"],
    )
    result = await asyncio.to_thread(llm, sp_final, up, model)
    r["result_final_analysis"] = result

    file_name = r["company_name"] + ".txt"
    full_path = os.path.join(INDIVIDUAL_DIR, file_name)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(result)
    log(f"Saved final analysis to: {full_path}")
    return True


_SYNTHESIS_DISCLAIMER = (
    "\n\n---\n"
    "⚠️ DATA SOURCE: LLM SYNTHESIS (NOT SEARCH-GROUNDED)\n"
    "Gemini Search was unavailable. This analysis was generated from training-data knowledge only — "
    "no live concall transcripts were fetched. Management guidance targets marked 'inferred' were not "
    "verified against actual earnings call transcripts. Treat this output as directional only.\n"
    "---\n"
)


async def _step_6(run_id, r, log, model):
    """Walk the Talk via Gemini Search (fallback to LLM synthesis)."""
    company_name = r["company_name"]

    try:
        from google.genai import types
        from backend.services.llm_service import get_gemini_client

        gemini_client = get_gemini_client()
        if gemini_client is None:
            raise ValueError("GOOGLE_API_KEY not set")

        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(
            tools=[grounding_tool],
            system_instruction=(
                "You are a financial research analyst with live web search access. "
                "Your job is to search for actual earnings call transcripts, investor presentations, "
                "and official financial filings to find real management guidance and outcomes. "
                "Always prefer data you find via search over anything in your training data. "
                "Do not add training-data disclaimers — you are search-grounded."
            ),
        )
        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=prompts.user_prompt_walkthetalk_search(company_name))],
            )
        ]
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=resolve_gemini_model_id(model), contents=contents, config=config
        )
        r["result_walkthetalk"] = response.text
        r["concall_source"] = "gemini_search"
        log("Gemini Search Walk the Talk successful (search-grounded).")
    except Exception as e:
        log(f"Gemini Search failed: {e}. Falling back to LLM synthesis (not grounded).")
        result = await asyncio.to_thread(
            llm,
            "You are a specialized financial data analyst.",
            prompts.user_prompt_walkthetalk(company_name),
            model,
        )
        r["result_walkthetalk"] = _SYNTHESIS_DISCLAIMER + result
        r["concall_source"] = "llm_synthesis"
        log("Walk the Talk generated via LLM synthesis — results are NOT search-grounded.")

    file_name = company_name + "_concall.txt"
    full_path = os.path.join(INDIVIDUAL_DIR, file_name)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(r["result_walkthetalk"])
    log(f"Saved Walk the Talk to: {full_path} [source: {r['concall_source']}]")
    return True


async def _step_7(run_id, r, log, sp_concall_score, model):
    """Concall credibility scoring."""
    company_name = r["company_name"]
    concall_text = clean_text_for_llm(r["result_walkthetalk"])
    data_source = r.get("concall_source", "llm_synthesis")
    up = prompts.prompt_concall_score(company_name, concall_text, data_source)
    result = await asyncio.to_thread(llm, sp_concall_score, up, model)
    r["result_concall_score"] = result

    file_name = company_name + "_concall_score.txt"
    full_path = os.path.join(INDIVIDUAL_DIR, file_name)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(result)
    log(f"Saved Concall Score to: {full_path} [source: {data_source}]")
    return True
