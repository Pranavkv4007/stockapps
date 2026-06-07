"""
8-phase sector pipeline — exact port from Fullscreener_app.py.
Runs asynchronously, pushes SSE events via PipelineManager.
"""

import os
import re
import json
import time
import asyncio
import pandas as pd

from backend.config import SECTOR_DIR
from backend.services.pipeline_manager import PipelineManager
from backend.services.llm_service import llm, llm_json
from backend.services.scraper_service import (
    Website, get_sector_details, get_company_names,
    get_subsector_details, get_sector_names,
)
from backend.services import prompts

mgr = PipelineManager()


async def run_sector_pipeline(
    run_id: str,
    url: str,
    model_screener: str = "gemini-flash",
    model_score: str = "gemini-flash",
    model_json: str = "gemini-flash",
    sp_screener: str = None,
    sp_score: str = None,
    sp_json: str = None,
):
    """Execute the full 8-phase sector pipeline."""
    run = mgr.get_run(run_id)
    if not run:
        return

    sp_screener = sp_screener or prompts.DEFAULT_SYSTEM_PROMPT_SCREENER
    sp_score = sp_score or prompts.DEFAULT_SYSTEM_PROMPT_SCORE
    sp_json = sp_json or prompts.DEFAULT_SYSTEM_PROMPT_JSON

    run.status = "running"
    log = lambda msg: mgr.add_log(run_id, msg)
    event = lambda t, d: mgr.push_event(run_id, t, d)

    try:
        # ── Phase 1: Scrape sector info ──
        run.phase = 0
        event("phase_start", {"phase": 0, "label": "Scraping sector information"})
        log("Phase 1: Scraping sector URL...")

        site = await asyncio.to_thread(Website, url)
        pages = site.get_pages()
        sector = site.get_title()

        log(f"Analysing: {sector}")
        log(f"Total pages: {pages}")

        # Create folder
        os.makedirs(SECTOR_DIR, exist_ok=True)
        try:
            folder_path = os.path.join(SECTOR_DIR, sector)
            os.makedirs(folder_path, exist_ok=True)
        except Exception:
            safe_name = re.sub(r'[<>:"/\\|?*;]', "_", sector)
            folder_path = os.path.join(SECTOR_DIR, safe_name)
            os.makedirs(folder_path, exist_ok=True)

        log(f"Folder: {folder_path}")
        event("phase_complete", {"phase": 0})

        if run.is_cancelled():
            return

        # ── Phase 2: Get company links ──
        run.phase = 1
        event("phase_start", {"phase": 1, "label": "Getting company links"})
        log("Phase 2: Getting company links...")

        def _get_links():
            return get_sector_details(url, pages, callback=lambda m: log(m))

        company_links = await asyncio.to_thread(_get_links)
        total_companies = len(company_links)
        log(f"Total companies: {total_companies}")
        event("phase_complete", {"phase": 1, "detail": f"Found {total_companies} companies"})

        if run.is_cancelled():
            return

        # ── Phase 3: Get company names ──
        run.phase = 2
        event("phase_start", {"phase": 2, "label": "Getting company names"})
        log("Phase 3: Getting company names...")

        def _get_names():
            return get_company_names(company_links, total_companies, callback=lambda m: log(m))

        company_list = await asyncio.to_thread(_get_names)
        company_dict = dict(zip(company_list, company_links))
        log(f"Companies: {', '.join(company_list)}")
        event("phase_complete", {"phase": 2, "detail": f"Named {len(company_list)} companies"})

        if run.is_cancelled():
            return

        # ── Phase 4: Get sector classification ──
        run.phase = 3
        event("phase_start", {"phase": 3, "label": "Getting sector classification"})
        log("Phase 4: Getting sector classification...")

        def _get_sector_info():
            last_site = Website(company_links[-1])
            market_links = get_subsector_details(last_site)
            return get_sector_names(market_links)

        sector_name, sub_sector = await asyncio.to_thread(_get_sector_info)
        log(f"Sector: {sector_name}, Sub-sector: {sub_sector}")
        event("phase_complete", {"phase": 3})

        if run.is_cancelled():
            return

        # ── Cache check: pause and ask user if existing files found ──
        existing_files = [
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
        ]
        if existing_files:
            run.status = "awaiting_cache_decision"
            log(f"Cache check: {len(existing_files)} existing file(s) found. Waiting for your decision...")
            event("cache_prompt", {"files": existing_files, "count": len(existing_files), "sector": sector})
            await run._cache_event.wait()

            if run.is_cancelled():
                return

            if run.cache_decision == "delete":
                for _f in existing_files:
                    _fp = os.path.join(folder_path, _f)
                    if os.path.isfile(_fp):
                        try:
                            os.remove(_fp)
                        except Exception:
                            pass
                log("Cache deleted. Starting fresh run.")
            else:
                log("Continuing with cached files.")

        if run.is_cancelled():
            return

        # ── Phase 5: Financial data extraction ──
        run.phase = 4
        event("phase_start", {"phase": 4, "label": "Extracting financial data"})
        log("Phase 5: Extracting financial data...")
        run_count = 0
        max_runs = 100

        for i in range(len(company_links)):
            if run.is_cancelled():
                return
            if run_count >= max_runs:
                break

            file_name = company_list[i] + ".txt"
            full_path = os.path.join(folder_path, file_name)
            run.progress = (i + 1) / total_companies
            run.progress_text = f"Extracting: {company_list[i]} ({i + 1}/{total_companies})"
            event("progress", {"progress": run.progress, "text": run.progress_text})

            if not os.path.exists(full_path):
                log(f"Analysing {company_list[i]} ({i + 1}/{total_companies})")
                await asyncio.to_thread(time.sleep, 1)
                try:
                    site_obj = await asyncio.to_thread(Website, company_links[i])
                    up = prompts.user_prompt_screener_sector(site_obj.text)
                    result = await asyncio.to_thread(llm, sp_screener, up, model_screener)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(result)
                    log(f"Saved {company_list[i]}")
                    run_count += 1
                except Exception as e:
                    log(f"ERROR extracting {company_list[i]}: {e}")
            else:
                log(f"Skipped {company_list[i]} — cached")

        event("phase_complete", {"phase": 4, "detail": f"Extracted {total_companies} companies"})

        if run.is_cancelled():
            return

        # ── Phase 6: Score calculation ──
        run.phase = 5
        event("phase_start", {"phase": 5, "label": "Calculating scores"})
        log("Phase 6: Calculating scores...")

        file_names = []
        file_contents = []
        for filename in os.listdir(folder_path):
            if filename.endswith(".txt") and not filename.endswith("_Score.txt"):
                fp = os.path.join(folder_path, filename)
                try:
                    size_kb = os.path.getsize(fp) / 1024
                    if size_kb > 100:
                        log(f"WARNING: Skipping {filename} — file too large ({size_kb:.1f} KB), likely corrupted extraction.")
                        continue
                    with open(fp, "r", encoding="utf-8") as f:
                        content = f.read()
                    file_names.append(os.path.splitext(filename)[0])
                    file_contents.append(content)
                except Exception as e:
                    log(f"Error reading {fp}: {e}")

        for i in range(len(file_names)):
            if run.is_cancelled():
                return

            base_name = file_names[i]
            score_full_path = os.path.join(folder_path, base_name + "_Score.txt")
            source_path = os.path.join(folder_path, base_name + ".txt")
            size_kb = os.path.getsize(source_path) / 1024 if os.path.exists(source_path) else 0

            run.progress = (i + 1) / len(file_names)
            run.progress_text = f"Scoring: {base_name} ({i + 1}/{len(file_names)})"
            event("progress", {"progress": run.progress, "text": run.progress_text})

            if os.path.exists(score_full_path) or size_kb > 20:
                log(f"Skipped scoring {base_name}")
                continue

            log(f"Scoring {base_name}")
            try:
                up = prompts.user_prompt_score(base_name, sector, file_contents[i])
                result = await asyncio.to_thread(llm, sp_score, up, model_score)
                await asyncio.to_thread(time.sleep, 1)
                with open(score_full_path, "w", encoding="utf-8") as f:
                    f.write(result)
                log(f"Saved score for {base_name}")
            except Exception as e:
                log(f"ERROR scoring {base_name}: {e}")

        event("phase_complete", {"phase": 5, "detail": f"Scored {len(file_names)} companies"})

        if run.is_cancelled():
            return

        # ── Phase 7: JSON creation ──
        run.phase = 6
        event("phase_start", {"phase": 6, "label": "Creating JSON summaries"})
        log("Phase 7: Creating JSON summaries...")

        score_file_names = []
        score_file_contents = []
        for filename in os.listdir(folder_path):
            if filename.endswith("_Score.txt"):
                fp = os.path.join(folder_path, filename)
                try:
                    size_kb = os.path.getsize(fp) / 1024
                    if size_kb > 100:
                        log(f"WARNING: Skipping {filename} — score file too large ({size_kb:.1f} KB), possibly corrupted.")
                        continue
                    with open(fp, "r", encoding="utf-8") as f:
                        content = f.read()
                    score_file_names.append(os.path.splitext(filename)[0])
                    score_file_contents.append(content)
                except Exception as e:
                    log(f"Error reading {fp}: {e}")

        # Resumability via progress.json
        progress_file = os.path.join(folder_path, "progress.json")
        if os.path.exists(progress_file):
            with open(progress_file, "r") as f:
                final_results = json.load(f)
            log(f"Resumed from progress. Already processed: {len(final_results)}")
        else:
            final_results = []

        start_index = len(final_results)
        for i in range(start_index, len(score_file_names)):
            if run.is_cancelled():
                return

            run.progress = (i + 1) / len(score_file_names)
            run.progress_text = f"JSON: {score_file_names[i]} ({i + 1}/{len(score_file_names)})"
            event("progress", {"progress": run.progress, "text": run.progress_text})
            log(f"JSON for {score_file_names[i]}")

            try:
                up = prompts.user_prompt_json(score_file_contents[i])
                content = await asyncio.to_thread(llm_json, sp_json, up, model_json)
                final_temp = json.loads(content)
                final_results.append(final_temp)
                with open(progress_file, "w") as f:
                    json.dump(final_results, f, indent=2)
                log(f"Processed: {score_file_names[i]}")
            except Exception as e:
                log(f"ERROR JSON for {score_file_names[i]}: {e}")

        event("phase_complete", {"phase": 6, "detail": f"Created JSON for {len(final_results)} companies"})

        if run.is_cancelled():
            return

        # ── Phase 8: Save final files ──
        run.phase = 7
        event("phase_start", {"phase": 7, "label": "Saving final results"})
        log("Phase 8: Saving final results...")

        # Save JSON
        json_file_name = sector + ".json"
        try:
            json_full_path = os.path.join(folder_path, json_file_name)
            with open(json_full_path, "w", encoding="utf-8") as jf:
                json.dump(final_results, jf, ensure_ascii=False, indent=2)
        except Exception:
            safe_name = re.sub(r'[<>:"/\\|?*;]', "_", sector)
            json_full_path = os.path.join(folder_path, safe_name + ".json")
            with open(json_full_path, "w", encoding="utf-8") as jf:
                json.dump(final_results, jf, ensure_ascii=False, indent=2)
        log(f"Saved JSON: {json_full_path}")

        # Build dataframe & save CSV
        score_df = None
        if final_results:
            df = pd.DataFrame(final_results)
            score_df = df[["company", "score"]].copy()
            score_df["Sector"] = sector
            score_df["url"] = score_df["company"].map(company_dict)
            score_df = score_df.sort_values(by="score", ascending=False)

            csv_file_name = sector + ".csv"
            try:
                csv_full_path = os.path.join(folder_path, csv_file_name)
                score_df.to_csv(csv_full_path, index=False, encoding="utf-8-sig")
            except Exception:
                safe_name = re.sub(r'[<>:"/\\|?*;]', "_", sector)
                csv_full_path = os.path.join(folder_path, safe_name + ".csv")
                score_df.to_csv(csv_full_path, index=False, encoding="utf-8-sig")
            log(f"Saved CSV: {csv_full_path}")

        score_records = []
        if score_df is not None:
            score_records = json.loads(score_df.to_json(orient="records"))

        run.results = {
            "sector": sector,
            "sector_name": sector_name,
            "sub_sector": sub_sector,
            "total_companies": total_companies,
            "company_list": company_list,
            "final_results_json": final_results,
            "score_data": score_records,
            "folder_path": folder_path,
        }

        run.status = "completed"
        run.progress = 1.0
        run.progress_text = "Pipeline completed!"
        log("Pipeline completed successfully!")
        event("phase_complete", {"phase": 7})
        event("done", {"message": "Pipeline completed successfully!"})

    except Exception as e:
        run.status = "failed"
        run.error = str(e)
        log(f"PIPELINE ERROR: {e}")
        event("error", {"message": str(e)})
