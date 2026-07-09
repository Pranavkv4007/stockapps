"""Parity audit: prompts, user-prompt generators, and frozen thresholds
across the Full App (canonical), the Streamlit apps, and the analyze-stock skill.

Usage:  .venv\\Scripts\\python.exe .claude\\skills\\prompt-sync\\audit_prompts.py [--diff]
        --diff  also print a unified diff for every DRIFTED item

Exit code = number of DRIFTED/MISSING items (0 = fully in sync).
"""
import ast
import difflib
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROMPTS_PY = os.path.join(ROOT, "Full App", "backend", "services", "prompts.py")
IND_APP = os.path.join(ROOT, "individual", "IndividualStockApp.py")
SEC_APP = os.path.join(ROOT, "FullScreener", "Fullscreener_app.py")
IND_SERVICE = os.path.join(ROOT, "Full App", "backend", "services", "individual_service.py")
SEC_SERVICE = os.path.join(ROOT, "Full App", "backend", "services", "sector_service.py")
IND_VIZ = os.path.join(ROOT, "Visualizations", "Individualscoreapp.py")
SEC_VIZ = os.path.join(ROOT, "Visualizations", "ScoreVisualApp.py")
SKILL_MD = os.path.join(ROOT, ".claude", "skills", "analyze-stock", "skill.md")

SHOW_DIFF = "--diff" in sys.argv

# (name in prompts.py, twin file, name in twin file)
SYSTEM_PROMPT_MAP = [
    ("DEFAULT_SYSTEM_PROMPT_SCREENER",      SEC_APP, "DEFAULT_SYSTEM_PROMPT_SCREENER"),
    ("DEFAULT_SYSTEM_PROMPT_SCORE",         SEC_APP, "DEFAULT_SYSTEM_PROMPT_SCORE"),
    ("DEFAULT_SYSTEM_PROMPT_JSON",          SEC_APP, "DEFAULT_SYSTEM_PROMPT_JSON"),
    ("DEFAULT_SYSTEM_PROMPT_SCREENER_IND",  IND_APP, "DEFAULT_SYSTEM_PROMPT_SCREENER"),
    ("DEFAULT_SYSTEM_PROMPT_JSON_IND",      IND_APP, "DEFAULT_SYSTEM_PROMPT_JSON"),
    ("DEFAULT_SYSTEM_PROMPT_KPI",           IND_APP, "DEFAULT_SYSTEM_PROMPT_KPI"),
    ("DEFAULT_SYSTEM_PROMPT_KPI_CAL",       IND_APP, "DEFAULT_SYSTEM_PROMPT_KPI_CAL"),
    ("DEFAULT_SYSTEM_PROMPT_GEMINI_SEARCH", IND_APP, "DEFAULT_SYSTEM_PROMPT_GEMINI_SEARCH"),
    ("DEFAULT_SYSTEM_PROMPT_FINAL",         IND_APP, "DEFAULT_SYSTEM_PROMPT_FINAL"),
    ("DEFAULT_SYSTEM_PROMPT_CONCALL_SCORE", IND_APP, "DEFAULT_SYSTEM_PROMPT_CONCALL_SCORE"),
]

# User-prompt generators: (name in prompts.py, name in twin app).
# NOTE: the *screener* pairs differ by design in plumbing (Full App takes
# pre-scraped site_text; Streamlit may scrape inline) — for those, DRIFTED
# means "inspect --diff and verify the prompt TEXT lines match", not auto-fail.
FUNC_MAP = [
    (SEC_APP, [("user_prompt_screener_sector", "user_prompt_screener"),
               ("user_prompt_score", "user_prompt_score"),
               ("user_prompt_json", "user_prompt_json")]),
    (IND_APP, [("user_prompt_screener_ind", "user_prompt_screener"),
               ("create_user_json", "create_user_json"),
               ("user_prompts_kpi", "user_prompts_kpi"),
               ("user_prompts_kpi_cal", "user_prompts_kpi_cal"),
               ("user_prompts_gemini_search", "user_prompts_gemini_search"),
               ("create_user_prompt_final", "create_user_prompt_final"),
               ("user_prompt_walkthetalk", "user_prompt_walkthetalk"),
               ("user_prompt_walkthetalk_search", "user_prompt_walkthetalk_search"),
               ("prompt_concall_score", "prompt_concall_score")]),
]

# Extraction/classification functions that must match between service and viz app.
LOGIC_FUNC_MAP = [
    (IND_SERVICE, IND_VIZ, ["extract_overall_score", "extract_credibility_score",
                            "assign_tier", "assign_signal"]),
    (SEC_SERVICE, SEC_VIZ, ["run_csv_combiner"]),
]

GUARD_BLOCKS = [
    ("TODAY'S DATE injection",            PROMPTS_PY, "TODAY'S DATE"),
    ("Actuals-not-projections guard",     PROMPTS_PY, "CRITICAL DATA INSTRUCTION"),
    ("Revenue-from-Operations guard",     PROMPTS_PY, "Revenue from Operations vs Total Income"),
    ("Guidance Period Assignment guard",  PROMPTS_PY, "Guidance Period Assignment"),
    ("PERIOD MISMATCH integrity check",   PROMPTS_PY, "PERIOD MISMATCH"),
    ("Fixed 5-dimension score table",     PROMPTS_PY, "KPI & Ratio Benchmark Performance | 40"),
    ("Data-confidence banner",            PROMPTS_PY, "Data Confidence"),
]

results = []  # (status, category, label, detail)


def parse(path):
    src = open(path, encoding="utf-8").read()
    return src, ast.parse(src)


def string_constants(tree):
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            out[node.targets[0].id] = node.value.value
    return out


def functions(src, tree):
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = ast.get_source_segment(src, node)
    return out


def norm(text):
    """Whitespace-normalized comparison form."""
    lines = [ln.strip() for ln in text.strip().splitlines()]
    return "\n".join(ln for ln in lines if ln)


def body_norm(func_src):
    """Function body only (drop the def line so decorators/signature spacing don't matter)."""
    lines = func_src.splitlines()
    # skip until the line ending the signature (first line ending with ':' at depth 0 is fine here)
    for i, ln in enumerate(lines):
        if ln.rstrip().endswith(":"):
            return norm("\n".join(lines[i + 1:]))
    return norm(func_src)


def show_diff(label, a, b, name_a, name_b):
    print(f"\n----- diff: {label} ({name_a} vs {name_b}) -----")
    for line in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=1):
        if line.startswith(("---", "+++")):
            continue
        print(line[:160])


def check(status, category, label, detail=""):
    results.append((status, category, label, detail))


# ── 1. System prompt constants ──────────────────────────────────────────
p_src, p_tree = parse(PROMPTS_PY)
p_consts = string_constants(p_tree)
p_funcs = functions(p_src, p_tree)

twin_cache = {}
for path in {SEC_APP, IND_APP}:
    twin_cache[path] = parse(path)

for canon_name, twin_path, twin_name in SYSTEM_PROMPT_MAP:
    t_src, t_tree = twin_cache[twin_path]
    t_consts = string_constants(t_tree)
    a, b = p_consts.get(canon_name), t_consts.get(twin_name)
    twin_label = os.path.basename(twin_path)
    if a is None:
        check("MISSING", "system-prompt", canon_name, "not found in prompts.py")
    elif b is None:
        check("MISSING", "system-prompt", canon_name, f"{twin_name} not found in {twin_label}")
    elif norm(a) == norm(b):
        check("IN SYNC", "system-prompt", canon_name, twin_label)
    else:
        check("DRIFTED", "system-prompt", canon_name, twin_label)
        if SHOW_DIFF:
            show_diff(canon_name, norm(a), norm(b), "prompts.py", twin_label)

# ── 2. User-prompt generator functions ─────────────────────────────────
for twin_path, pairs in FUNC_MAP:
    t_src, t_tree = twin_cache[twin_path]
    t_funcs = functions(t_src, t_tree)
    twin_label = os.path.basename(twin_path)
    for canon_name, twin_name in pairs:
        a, b = p_funcs.get(canon_name), t_funcs.get(twin_name)
        if a is None or b is None:
            where = "prompts.py" if a is None else twin_label
            check("MISSING", "user-prompt-fn", canon_name, f"not found in {where}")
        elif body_norm(a) == body_norm(b):
            check("IN SYNC", "user-prompt-fn", canon_name, twin_label)
        else:
            check("DRIFTED", "user-prompt-fn", canon_name, twin_label)
            if SHOW_DIFF:
                show_diff(canon_name, body_norm(a), body_norm(b), "prompts.py", twin_label)

# ── 3. Extraction/classification logic parity ──────────────────────────
for svc_path, viz_path, names in LOGIC_FUNC_MAP:
    s_src, s_tree = parse(svc_path)
    v_src, v_tree = parse(viz_path)
    s_funcs, v_funcs = functions(s_src, s_tree), functions(v_src, v_tree)
    pair = f"{os.path.basename(svc_path)} vs {os.path.basename(viz_path)}"
    for name in names:
        a, b = s_funcs.get(name), v_funcs.get(name)
        if a is None or b is None:
            check("MISSING", "logic-fn", name, pair)
        elif body_norm(a) == body_norm(b):
            check("IN SYNC", "logic-fn", name, pair)
        else:
            check("DRIFTED", "logic-fn", name, pair)
            if SHOW_DIFF:
                show_diff(name, body_norm(a), body_norm(b),
                          os.path.basename(svc_path), os.path.basename(viz_path))

# ── 4. Frozen constants presence ────────────────────────────────────────
def contains(path, needle):
    try:
        return needle in open(path, encoding="utf-8").read()
    except OSError:
        return False

for path, label in [(IND_SERVICE, "individual_service.py"), (IND_VIZ, "Individualscoreapp.py")]:
    ok = all(contains(path, s) for s in [">= 80", ">= 60", ">= 40", ">= 75", "< 50"])
    check("IN SYNC" if ok else "DRIFTED", "thresholds", f"tier/signal cutoffs in {label}",
          "80/60/40 tiers, 75/60/50 signals")

for path, label in [(SEC_SERVICE, "sector_service.py"), (SEC_VIZ, "ScoreVisualApp.py")]:
    ok = contains(path, "/ 10) * 10") or contains(path, "/10)*10")
    check("IN SYNC" if ok else "DRIFTED", "thresholds", f"floor(max/10)*10 in {label}")

# Financial scoring weights everywhere they appear
WEIGHT_RE = re.compile(r"KPI\s*&\s*Ratio Benchmark Performance[^\n]*40")
for path, label in [(PROMPTS_PY, "prompts.py"), (IND_APP, "IndividualStockApp.py"),
                    (SKILL_MD, "analyze-stock skill")]:
    ok = bool(WEIGHT_RE.search(open(path, encoding="utf-8").read()))
    check("IN SYNC" if ok else "DRIFTED", "thresholds",
          f"40/20/15/15/10 weights in {label}", "KPI benchmark = 40")

# ── 5. Guard blocks present in canonical prompts ────────────────────────
for label, path, needle in GUARD_BLOCKS:
    ok = contains(path, needle)
    check("IN SYNC" if ok else "MISSING", "guard-block", label, needle)

# ── Report ───────────────────────────────────────────────────────────────
print(f"\n{'='*74}\nPROMPT / LOGIC PARITY AUDIT — root: {ROOT}\n{'='*74}")
bad = 0
for category in ["system-prompt", "user-prompt-fn", "logic-fn", "thresholds", "guard-block"]:
    rows = [r for r in results if r[1] == category]
    if not rows:
        continue
    print(f"\n[{category}]")
    for status, _, label, detail in rows:
        mark = "OK " if status == "IN SYNC" else "!! "
        if status != "IN SYNC":
            bad += 1
        print(f"  {mark}{status:<8} {label:<45} {detail}")

print(f"\n{'='*74}")
print("RESULT: FULLY IN SYNC" if bad == 0 else
      f"RESULT: {bad} item(s) DRIFTED/MISSING — rerun with --diff to inspect")
sys.exit(min(bad, 99))
