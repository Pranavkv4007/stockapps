"""
Backend integration test script.
Tests all pipeline endpoints and service imports without requiring API keys.
Run: python test_backend.py
"""

import os
import sys
import json
import asyncio
import importlib

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

results = {"pass": 0, "fail": 0, "skip": 0}


def test(name, fn):
    try:
        result = fn()
        if result == "skip":
            print(f"  [{SKIP}] {name}")
            results["skip"] += 1
        else:
            print(f"  [{PASS}] {name}")
            results["pass"] += 1
    except Exception as e:
        print(f"  [{FAIL}] {name}: {e}")
        results["fail"] += 1


def main():
    print("=" * 60)
    print("Stock Analysis Hub — Backend Integration Tests")
    print("=" * 60)

    # ── 1. Config ──
    print("\n1. Config")
    def test_config():
        from backend.config import (
            SECTOR_DIR, INDIVIDUAL_DIR, OPENAI_MODEL, GPT4O,
            GEMINI_MODEL, MODEL_OPTIONS, HUB_ROOT,
        )
        assert OPENAI_MODEL == "gpt-4.1-mini-2025-04-14"
        assert GPT4O == "gpt-4o-mini-2024-07-18"
        assert GEMINI_MODEL == "gemini-3-pro-preview"
        assert MODEL_OPTIONS == ["gemini", "openai", "gpt4o"]
        assert os.path.isabs(SECTOR_DIR)
        assert os.path.isabs(INDIVIDUAL_DIR)
    test("Config constants loaded", test_config)

    # ── 2. LLM Service ──
    print("\n2. LLM Service")
    def test_llm_import():
        from backend.services.llm_service import (
            get_openai_client, get_gemini_client, build_prompt,
            llm, llm_json, gemini_llm_kpi, clean_and_parse_json,
            clean_text_for_llm, check_api_status,
        )
    test("LLM service imports", test_llm_import)

    def test_build_prompt():
        from backend.services.llm_service import build_prompt
        gemini = build_prompt("sys", "user", "gemini")
        assert isinstance(gemini, str) and "sys" in gemini and "user" in gemini
        openai = build_prompt("sys", "user", "openai")
        assert isinstance(openai, list) and len(openai) == 2
        gpt4o = build_prompt("sys", "user", "gpt4o")
        assert isinstance(gpt4o, list)
        none_result = build_prompt("sys", "user", "unknown")
        assert none_result is None
    test("build_prompt() all model types", test_build_prompt)

    def test_clean_parse_json():
        from backend.services.llm_service import clean_and_parse_json
        assert clean_and_parse_json('```json\n{"a": 1}\n```') == {"a": 1}
        assert clean_and_parse_json('{"b": 2}') == {"b": 2}
        assert clean_and_parse_json('not json') is None
    test("clean_and_parse_json()", test_clean_parse_json)

    def test_clean_text():
        from backend.services.llm_service import clean_text_for_llm
        text = "Hello [cite:123] world 🔴 test\n\n\n\nextra"
        cleaned = clean_text_for_llm(text)
        assert "[cite:" not in cleaned
        assert "\n\n\n" not in cleaned
    test("clean_text_for_llm()", test_clean_text)

    # ── 3. Scraper Service ──
    print("\n3. Scraper Service")
    def test_scraper_import():
        from backend.services.scraper_service import (
            Website, get_sector_details, get_company_names,
            get_subsector_details, get_sector_names, HEADERS,
        )
        assert "User-Agent" in HEADERS
    test("Scraper service imports", test_scraper_import)

    # ── 4. Prompts ──
    print("\n4. Prompts")
    def test_prompts_sector():
        from backend.services.prompts import (
            DEFAULT_SYSTEM_PROMPT_SCREENER, DEFAULT_SYSTEM_PROMPT_SCORE,
            DEFAULT_SYSTEM_PROMPT_JSON, user_prompt_screener_sector,
            user_prompt_score, user_prompt_json, SECTOR_DEFAULTS,
        )
        assert "financial data extraction" in DEFAULT_SYSTEM_PROMPT_SCREENER.lower()
        assert "score" in DEFAULT_SYSTEM_PROMPT_SCORE.lower()
        assert "json" in DEFAULT_SYSTEM_PROMPT_JSON.lower()
        up = user_prompt_screener_sector("test data")
        assert "test data" in up
        up2 = user_prompt_score("CompanyX", "Tech", "financials here")
        assert "CompanyX" in up2 and "Tech" in up2
        up3 = user_prompt_json("some result")
        assert "some result" in up3
        assert len(SECTOR_DEFAULTS) == 3
    test("Sector prompts (3 system + 3 user generators)", test_prompts_sector)

    def test_prompts_individual():
        from backend.services.prompts import (
            DEFAULT_SYSTEM_PROMPT_SCREENER_IND, DEFAULT_SYSTEM_PROMPT_JSON_IND,
            DEFAULT_SYSTEM_PROMPT_KPI, DEFAULT_SYSTEM_PROMPT_KPI_CAL,
            DEFAULT_SYSTEM_PROMPT_GEMINI_SEARCH, DEFAULT_SYSTEM_PROMPT_FINAL,
            DEFAULT_SYSTEM_PROMPT_CONCALL_SCORE,
            user_prompt_screener_ind, create_user_json, user_prompts_kpi,
            user_prompts_kpi_cal, user_prompts_gemini_search,
            create_user_prompt_final, user_prompt_walkthetalk,
            prompt_concall_score, INDIVIDUAL_DEFAULTS,
        )
        assert len(INDIVIDUAL_DEFAULTS) == 7
        assert "CompanyY" in user_prompt_walkthetalk("CompanyY")
        assert "CompanyZ" in prompt_concall_score("CompanyZ", "analysis text")
        up = user_prompts_kpi("Banking", "Private Banks")
        assert "Banking" in up
    test("Individual prompts (7 system + 8 user generators)", test_prompts_individual)

    # ── 5. Pipeline Manager ──
    print("\n5. Pipeline Manager")
    def test_pipeline_manager():
        from backend.services.pipeline_manager import PipelineManager, PipelineRun
        mgr = PipelineManager()
        # Create run
        run = mgr.create_run("sector")
        assert run.run_id
        assert run.pipeline_type == "sector"
        assert run.status == "pending"
        # Get run
        fetched = mgr.get_run(run.run_id)
        assert fetched is run
        # List runs
        runs = mgr.list_runs()
        assert any(r["run_id"] == run.run_id for r in runs)
        # Add log
        mgr.add_log(run.run_id, "test message")
        assert len(run.logs) >= 1
        assert "test message" in run.logs[-1]
        # Cancel
        run.status = "running"
        assert mgr.cancel_run(run.run_id) is True
        assert run.status == "cancelled"
        assert run.is_cancelled()
    test("PipelineManager create/get/list/log/cancel", test_pipeline_manager)

    def test_pipeline_singleton():
        from backend.services.pipeline_manager import PipelineManager
        m1 = PipelineManager()
        m2 = PipelineManager()
        assert m1 is m2
    test("PipelineManager is singleton", test_pipeline_singleton)

    # ── 6. Sector Pipeline ──
    print("\n6. Sector Pipeline")
    def test_sector_pipeline_import():
        from backend.services.sector_pipeline import run_sector_pipeline
        assert asyncio.iscoroutinefunction(run_sector_pipeline)
    test("Sector pipeline imports & is async", test_sector_pipeline_import)

    # ── 7. Individual Pipeline ──
    print("\n7. Individual Pipeline")
    def test_individual_pipeline_import():
        from backend.services.individual_pipeline import (
            run_individual_pipeline, STEP_LABELS, STEP_DEPS,
        )
        assert asyncio.iscoroutinefunction(run_individual_pipeline)
        assert len(STEP_LABELS) == 8
        assert len(STEP_DEPS) == 8
    test("Individual pipeline imports & is async", test_individual_pipeline_import)

    # ── 8. Pipeline Router ──
    print("\n8. Pipeline Router")
    def test_router_import():
        from backend.routers.pipeline import router
        routes = [r.path for r in router.routes]
        expected = [
            "/api/pipeline/sector/start", "/api/pipeline/individual/start",
            "/api/pipeline/individual/run-step",
            "/api/pipeline/stream/{run_id}", "/api/pipeline/status/{run_id}",
            "/api/pipeline/cancel/{run_id}",
            "/api/pipeline/runs", "/api/pipeline/api-status",
            "/api/pipeline/prompts/sector/defaults",
            "/api/pipeline/prompts/individual/defaults",
        ]
        for ep in expected:
            assert ep in routes, f"Missing route: {ep}"
    test("Pipeline router has all 10 endpoints", test_router_import)

    # ── 9. Main app ──
    print("\n9. Main App")
    def test_main_app():
        from backend.main import app
        route_paths = [r.path for r in app.routes]
        assert "/api/health" in route_paths
        # Check pipeline router is mounted
        assert any("/api/pipeline" in str(r.path) for r in app.routes)
    test("FastAPI app includes pipeline router", test_main_app)

    # ── 10. Requirements ──
    print("\n10. Requirements")
    def test_requirements():
        req_path = os.path.join(PROJECT_ROOT, "backend", "requirements.txt")
        with open(req_path, "r") as f:
            content = f.read()
        for pkg in ["fastapi", "uvicorn", "pandas", "python-dotenv", "requests", "beautifulsoup4", "openai", "google-genai"]:
            assert pkg in content, f"Missing package: {pkg}"
    test("requirements.txt has all 8 packages", test_requirements)

    # ── 11. FastAPI endpoint tests (using TestClient) ──
    print("\n11. API Endpoint Tests (TestClient)")
    try:
        from fastapi.testclient import TestClient
        from backend.main import app
        client = TestClient(app)

        def test_health():
            r = client.get("/api/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"
        test("GET /api/health", test_health)

        def test_pipeline_runs():
            r = client.get("/api/pipeline/runs")
            assert r.status_code == 200
            assert "runs" in r.json()
        test("GET /api/pipeline/runs", test_pipeline_runs)

        def test_sector_defaults():
            r = client.get("/api/pipeline/prompts/sector/defaults")
            assert r.status_code == 200
            data = r.json()
            assert "screener" in data and "score" in data and "json" in data
        test("GET /api/pipeline/prompts/sector/defaults", test_sector_defaults)

        def test_individual_defaults():
            r = client.get("/api/pipeline/prompts/individual/defaults")
            assert r.status_code == 200
            data = r.json()
            assert len(data) == 7
        test("GET /api/pipeline/prompts/individual/defaults", test_individual_defaults)

        def test_pipeline_status_not_found():
            r = client.get("/api/pipeline/status/nonexistent")
            assert r.status_code == 200
            assert r.json().get("error") == "Run not found"
        test("GET /api/pipeline/status/{bad_id} returns error", test_pipeline_status_not_found)

        def test_cancel_not_found():
            r = client.post("/api/pipeline/cancel/nonexistent")
            assert r.status_code == 200
            assert "error" in r.json()
        test("POST /api/pipeline/cancel/{bad_id} returns error", test_cancel_not_found)

        def test_api_status_endpoint():
            # This will likely fail without API keys, but should return 200
            r = client.get("/api/pipeline/api-status")
            assert r.status_code == 200
            assert "models" in r.json()
        test("GET /api/pipeline/api-status (structure check)", test_api_status_endpoint)

    except ImportError:
        print(f"  [{SKIP}] TestClient not available (install httpx)")
        results["skip"] += 1

    # ── 12. Frontend check ──
    print("\n12. Frontend")
    def test_frontend():
        html_path = os.path.join(PROJECT_ROOT, "frontend", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        checks = [
            ("marked.js CDN", "marked.min.js"),
            ("Sector Pipeline nav button", "sectorPipeline"),
            ("Individual Pipeline nav button", "individualPipeline"),
            ("SSE connectSSE function", "connectSSE"),
            ("startSectorPipeline function", "startSectorPipeline"),
            ("startIndividualPipeline function", "startIndividualPipeline"),
            ("renderMd function", "renderMd"),
            ("Keyboard shortcut 4", "key === '4'"),
            ("Keyboard shortcut 5", "key === '5'"),
        ]
        for label, needle in checks:
            assert needle in content, f"Missing in HTML: {label}"
    test("Frontend HTML contains all pipeline elements", test_frontend)

    # ── Summary ──
    print("\n" + "=" * 60)
    total = results["pass"] + results["fail"] + results["skip"]
    print(f"Results: {results['pass']}/{total} passed, {results['fail']} failed, {results['skip']} skipped")
    if results["fail"] == 0:
        print("\033[92mAll tests passed!\033[0m")
    else:
        print(f"\033[91m{results['fail']} test(s) failed.\033[0m")
    print("=" * 60)
    return results["fail"]


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
