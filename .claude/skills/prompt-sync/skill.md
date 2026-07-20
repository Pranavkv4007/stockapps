---
name: prompt-sync
description: Audit or apply prompt, threshold, and classification-logic changes across every duplicated copy in the monorepo (Full App prompts.py, Streamlit apps, Visualizations, prompts/ docs, analyze-stock skill). Use when editing any pipeline prompt, scoring weight, tier/signal threshold, or extraction regex, or when asked to check prompt parity/drift/sync.
---

Keeps the monorepo's duplicated prompt/logic copies identical. The repo's #1 failure mode is editing one copy and forgetting the others (see CLAUDE.md Law #1). This skill has two modes.

## Mode 1 — Audit (`/prompt-sync` or `/prompt-sync audit`)

Run the bundled script with the project venv:

```powershell
.venv\Scripts\python.exe .claude\skills\prompt-sync\audit_prompts.py
```

- Exit code 0 = fully in sync. Non-zero = number of drifted/missing items.
- Rerun with `--diff` to see unified diffs of each drifted item.
- Report results to the user as a table grouped by category (system prompts / user-prompt functions / logic functions / thresholds / guard blocks), listing only non-IN-SYNC items in detail.

Interpreting statuses:
- **DRIFTED system prompt or user-prompt fn** — sync direction is `prompts.py` → Streamlit copy (prompts.py is canonical and usually ahead; confirm with `git log -p` on both files if unsure which side has the newer guard).
- **DRIFTED logic fn** — `individual_service.py` / `sector_service.py` vs the Visualizations apps. These were "faithful ports"; drift usually means a fix landed in one side only. Inspect the diff before choosing a direction — NEVER resolve by simplifying regexes (CLAUDE.md Trap #2).
- **MISSING guard block** — a critical prompt guard was deleted. Treat as a regression; restore it from git history.
- Known cosmetic noise: `assign_*` or extraction functions may drift by docstrings/type hints only. If the `--diff` output shows no behavioral difference, report it as "cosmetic drift" and leave it (or align comments if already editing the file).

## Mode 2 — Synchronized edit (`/prompt-sync <change description>`)

Protocol for applying a prompt/threshold change everywhere:

1. **Audit first.** Run the script. If the target artifact is already drifted, resolve that drift FIRST (or at least report it) — otherwise your edit compounds the divergence.
2. **Locate all copies** using the copy map in root CLAUDE.md (Law #1 table). Special cases:
   - `*_SCREENER_IND` / `*_JSON_IND` in prompts.py are named `*_SCREENER` / `*_JSON` inside `individual/IndividualStockApp.py`.
   - Walk-the-Talk guards go in THREE places: `user_prompt_walkthetalk`, `user_prompt_walkthetalk_search`, and (when it concerns concall scoring context) `individual/transcript_scorer.py::_build_user_prompt`.
   - Weight/threshold changes also touch `.claude/skills/analyze-stock/skill.md` — but changing weights/thresholds at all requires the user's explicit confirmation (frozen constants).
3. **Edit canonical first** (`Full App/backend/services/prompts.py`), following house style: guards are appended as loud `**CRITICAL ... (non-negotiable)**` blocks with an EXAMPLE and a SELF-CHECK line; never rewrite or trim existing guard text.
4. **Propagate verbatim** to the Streamlit copy/copies. The text must be identical after whitespace normalization — copy the exact block, don't paraphrase.
5. **Update the docs copy**: `prompts/individual_pipeline.md` or `prompts/sector_pipeline.md`.
6. **Re-run the audit.** The edited artifact must now report IN SYNC and no guard block may be MISSING. Non-zero exit for unrelated pre-existing drift is acceptable — say so explicitly.
7. **Remind about the cache.** A prompt change has zero effect on cached files. Tell the user which caches to invalidate:
   - Step 1 / Phase 5 extraction prompts → `Sector/{sub_sector}/{Company}.txt`
   - Final analysis / Walk-the-Talk / concall prompts → `Individual_Stocks/{Company}*.txt`
   - Offer `/rerun-stock <company>` to verify the change end-to-end (that skill handles deletion + rerun + before/after scores).
8. **Commit** with all copies in one commit; body notes which files were synced and (if a verification run happened) the before → after score.

## What this skill must never do

- Change tier/signal thresholds, scoring weights, achievement bands, or the floor filter without the user's explicit request and confirmation.
- "Fix" extraction regexes to look cleaner — the mojibake patterns (`dYY.` etc.) are load-bearing.
- Resolve drift by deleting the richer version. When in doubt which side is newer, check `git log -p` and ask the user.
