# Transcript RAG Prompts

Used in `individual/transcript_scorer.py`. Provides RAG-based (Retrieval-Augmented Generation) credibility scoring from uploaded earnings call transcripts (.txt / .pdf).

**System prompt:** Reuses `DEFAULT_SYSTEM_PROMPT_CONCALL_SCORE` from `individual_pipeline.md` (Step 7). See that file for the full text.

---

## Scoring Category Retrieval Queries — `SCORING_QUERIES`

These queries drive the embedding-based retrieval step. Each tuple is `(category_name, retrieval_query)`. Retrieved chunks are organized by category and injected into the user prompt as `{retrieved_context}`.

| Category | Retrieval Query Keywords |
|----------|--------------------------|
| Revenue Guidance & Performance | management revenue guidance forecast target outlook and actual revenue sales turnover topline performance results growth year-over-year quarterly |
| EBITDA/Margin Guidance & Performance | management EBITDA margin operating margin gross margin profitability guidance target and actual margin performance expansion contraction basis points |
| Product Launch Commitments | new product launch pipeline R&D commercialization timeline delivery commitment rollout schedule capacity expansion capex commissioning |
| Strategic Initiatives | strategic initiative acquisition merger partnership JV market entry digital transformation cost optimization restructuring execution progress update |
| Regulatory/Approval Targets | regulatory approval license compliance SEBI RBI FSSAI FDA clearance environmental permit milestone government policy order |
| Management Credibility & Transparency | management commentary tone guidance revision downgrade upgrade honest transparent conservative aggressive miss shortfall explanation accountability |
| Future Outlook & Growth | forward guidance next quarter next year outlook order book pipeline backlog demand momentum secular trend future growth projection medium-term long-term aspiration |

---

## User Prompt Template — `_build_user_prompt(company_name, retrieved_context)`

**Dynamic variables:**
- `{company_name}` — the company being analyzed
- `{retrieved_context}` — structured text assembled from RAG retrieval, organized into sections by category name (e.g., `### Revenue Guidance & Performance:\n...`)

```
## "Walk the Talk" Credibility Analysis — {company_name}

You are provided with **selected excerpts** from one or more earnings conference call transcripts of {company_name}. The excerpts have been pre-organized by scoring category below. These are the most relevant passages — not the full transcript.

**Important instructions for working with these excerpts:**
- Excerpts are fragments; cross-reference across categories where the same metric appears in multiple sections.
- Management statements from the Q&A portion carry equal weight to prepared remarks.
- When excerpts mention specific numbers (revenue guidance of ₹X Cr, margin target of Y%), treat those as concrete commitments.
- If an excerpt contains both a forward-looking guidance AND a backward-looking result, capture both — the guidance becomes the target and the result becomes the actual for that or the prior period.
- Where actual outcomes are not present in the excerpts, note it as "Actual not available in transcript" rather than guessing.

---

{retrieved_context}

---

### Analysis Required (apply the Scoring Framework from your system instructions):

**1. Guidance vs Delivery Table**
For every quantifiable commitment found in the excerpts, create a row:
| Period | Category (Weight) | Management Guidance | Actual Outcome | Achievement % | Status | Score | Weighted Contribution |

- Map each row to one of the 5 weighted categories: Revenue (30%), EBITDA/Margin (25%), Product Launches (20%), Strategic Initiatives (15%), Regulatory/Approvals (10%).
- Use the Achievement Categories from your scoring framework (Overachieved/Achieved/Nearly Met/Missed).
- If the transcript covers multiple quarters or years, include a row per period per metric.

**2. Weighted Credibility Score**
- Calculate the final weighted score using the weights above.
- Apply a **recency bias**: guidance from the most recent period should carry ~1.5x the weight of older periods when multiple periods are available.
- State the score interpretation band (Exceptional / Strong / Moderate / Weak / Poor).

**3. Qualitative Credibility Signals**
From the management tone and language in the excerpts, assess:
- **Guidance pattern**: Does management consistently guide conservatively and beat? Or guide aggressively and miss?
- **Revision transparency**: When guidance is revised, do they acknowledge the miss clearly or deflect?
- **Specificity**: Are commitments vague ("we expect growth") or precise ("we target 18-20% EBITDA margin by Q4")?
- **Accountability language**: Do they own misses ("we fell short on...") or externalize ("macro headwinds impacted...")?

**4. Concall-Specific Red Flags & Green Flags**
Identify from the excerpts:
- 🔴 Repeated guidance misses on the same metric across periods
- 🔴 Vague deflections in Q&A when analysts press on missed targets
- 🔴 Guidance range widening over time (increasing uncertainty)
- 🟢 Consistent beat-and-raise pattern
- 🟢 Proactive disclosure of challenges before analysts ask
- 🟢 Narrowing guidance ranges (increasing confidence)

**5. Investment Implications**
- What does the credibility score mean for forward estimates? Should sell-side consensus be trusted?
- Key metrics to monitor in the next earnings call.
- Risk-adjusted view: if credibility is low, what discount should be applied to stated guidance?

**6. Executive Summary**
- **Overall Credibility Score: X/100** with interpretation band
- **Data Confidence**: High / Medium / Low — based on how many concrete guidance-vs-actual pairs were extractable from the excerpts
- Top 3 credibility strengths
- Top 3 credibility concerns
- One-paragraph investment context
```

---

## RAG Pipeline Flow

```
Uploaded .txt/.pdf files
        │
        ▼
extract_text_from_files() / extract_text_from_paths()
        │
        ▼
_clean_text_for_llm()   ← removes citations, emojis, broken table rows
        │
        ▼
chunk_text()            ← RecursiveCharacterTextSplitter (chunk=1000, overlap=200)
        │
        ▼
build_retrieval_context()
  ├─ OpenAIEmbeddings → ephemeral Chroma vectorstore
  └─ For each SCORING_QUERIES entry: similarity_search(k=5) → deduplicate
        │
        ▼
retrieved_context       ← structured sections by category
        │
        ▼
_build_user_prompt(company_name, retrieved_context)
        │
        ▼
LLM call (system: CONCALL_SCORE, user: above prompt)
        │
        ▼
Credibility score report (markdown)
```
