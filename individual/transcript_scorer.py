"""
Transcript Scorer Module — RAG-based concall transcript scoring.

Extracts text from uploaded files, chunks it, uses embedding-based retrieval
to pull relevant sections per scoring category, then sends focused context
to the LLM for credibility scoring.
"""

import os
import re
import uuid


# ---------------------------------------------------------------------------
# Scoring-category retrieval queries (mapped to the weighting system)
# ---------------------------------------------------------------------------
SCORING_QUERIES = [
    ("Revenue Guidance & Performance",
     "management revenue guidance forecast target outlook and actual revenue sales turnover topline performance results growth year-over-year quarterly"),
    ("EBITDA/Margin Guidance & Performance",
     "management EBITDA margin operating margin gross margin profitability guidance target and actual margin performance expansion contraction basis points"),
    ("Product Launch Commitments",
     "new product launch pipeline R&D commercialization timeline delivery commitment rollout schedule capacity expansion capex commissioning"),
    ("Strategic Initiatives",
     "strategic initiative acquisition merger partnership JV market entry digital transformation cost optimization restructuring execution progress update"),
    ("Regulatory/Approval Targets",
     "regulatory approval license compliance SEBI RBI FSSAI FDA clearance environmental permit milestone government policy order"),
    ("Management Credibility & Transparency",
     "management commentary tone guidance revision downgrade upgrade honest transparent conservative aggressive miss shortfall explanation accountability"),
    ("Future Outlook & Growth",
     "forward guidance next quarter next year outlook order book pipeline backlog demand momentum secular trend future growth projection medium-term long-term aspiration"),
]


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------
def extract_text_from_files(uploaded_files) -> str:
    """Read uploaded Streamlit UploadedFile objects (.txt / .pdf) and return combined text."""
    texts = []
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            from PyPDF2 import PdfReader
            reader = PdfReader(uf)
            pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            texts.append(pdf_text)
        else:
            texts.append(uf.read().decode("utf-8", errors="replace"))
    return "\n\n".join(texts)


def extract_text_from_paths(file_paths: list[str]) -> str:
    """Read .txt / .pdf files from disk paths and return combined text."""
    texts = []
    for fp in file_paths:
        if fp.lower().endswith(".pdf"):
            from PyPDF2 import PdfReader
            reader = PdfReader(fp)
            pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            texts.append(pdf_text)
        else:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                texts.append(f.read())
    return "\n\n".join(texts)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks using LangChain's RecursiveCharacterTextSplitter."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------
def build_retrieval_context(chunks: list[str], openai_api_key: str, top_k: int = 5) -> str:
    """
    Embed chunks, store in an ephemeral Chroma collection, retrieve top-K
    chunks per scoring category, deduplicate, and return structured context.
    """
    from langchain_openai import OpenAIEmbeddings
    from langchain_chroma import Chroma

    embeddings = OpenAIEmbeddings(api_key=openai_api_key)

    collection_name = f"transcript_{uuid.uuid4().hex[:8]}"
    vectorstore = Chroma.from_texts(
        texts=chunks,
        embedding=embeddings,
        collection_name=collection_name,
    )

    try:
        sections = []
        seen_chunks = set()

        for category_name, query in SCORING_QUERIES:
            results = vectorstore.similarity_search(query, k=top_k)
            category_chunks = []
            for doc in results:
                content = doc.page_content.strip()
                if content not in seen_chunks:
                    seen_chunks.add(content)
                    category_chunks.append(content)

            section_text = "\n\n".join(category_chunks) if category_chunks else "(No relevant excerpts found)"
            sections.append(f"### {category_name}:\n{section_text}")

        return "\n\n".join(sections)
    finally:
        # Clean up the ephemeral collection
        try:
            vectorstore.delete_collection()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def _build_user_prompt(company_name: str, retrieved_context: str) -> str:
    """Build the user prompt with RAG-retrieved context organized by scoring category."""
    return f"""## "Walk the Talk" Credibility Analysis — {company_name}

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
"""


# ---------------------------------------------------------------------------
# Clean text helper (duplicated logic from main app to avoid circular import)
# ---------------------------------------------------------------------------
def _clean_text_for_llm(text: str) -> str:
    """Remove citations, emojis, broken table rows, and normalize whitespace."""
    text = re.sub(r"\[cite:.*?\]", "", text)
    text = re.sub(r"[🔴🟢🟡🔵⚪⚫🟠🟣🟤✅❌⭐]", "", text)
    text = re.sub(r"\n\s*:[-:|\s]+\n", "\n", text)
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        if "|" in line:
            cells = line.split("|")
            if any(len(cell.strip()) > 500 for cell in cells):
                continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"#{4,}", "###", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def score_transcript(uploaded_files, company_name: str, model_name: str,
                     llm_fn, system_prompt: str, openai_api_key: str,
                     file_paths: list[str] | None = None) -> str:
    """
    End-to-end transcript scoring with RAG retrieval.

    Parameters
    ----------
    uploaded_files : list of Streamlit UploadedFile objects (can be empty/None)
    company_name : str
    model_name : str — model key for llm_fn (e.g. "openai", "gemini", "gpt4o")
    llm_fn : callable(system_prompt, user_prompt, model_name) -> str
    system_prompt : str — the concall scoring system prompt
    openai_api_key : str — needed for embeddings
    file_paths : list of str — disk paths to .txt/.pdf files (optional, combined with uploaded_files)

    Returns
    -------
    str — LLM-generated credibility score analysis
    """
    # 1. Extract text from uploaded files and/or disk paths
    parts = []
    if uploaded_files:
        parts.append(extract_text_from_files(uploaded_files))
    if file_paths:
        parts.append(extract_text_from_paths(file_paths))
    raw_text = "\n\n".join(parts)
    if not raw_text.strip():
        raise ValueError("No readable text found in uploaded files or transcripts folder.")

    # 2. Clean text
    cleaned_text = _clean_text_for_llm(raw_text)

    # 3. Chunk
    chunks = chunk_text(cleaned_text)

    # 4. RAG retrieval — build focused context organized by scoring category
    retrieved_context = build_retrieval_context(chunks, openai_api_key)

    # 5. Build prompt and call LLM
    user_prompt = _build_user_prompt(company_name, retrieved_context)
    result = llm_fn(system_prompt, user_prompt, model_name)

    return result
