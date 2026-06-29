"""
Step 3: Gap analysis.

For a given project, looks at all the structured-knowledge extractions
belonging to that project's documents and asks: which of the standard
knowledge-transfer categories are covered, missing, or thin?

This is intentionally simpler than embedding-clustering -- it asks the LLM
directly, against a fixed checklist, which is faster to build and easier to
explain in a demo. The fixed category list is also the main limitation:
it won't catch gaps outside this list. See note at bottom for how to extend.
"""
import json
import os
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from src.extract import get_client, EXTRACTION_MODEL

load_dotenv()

STANDARD_CATEGORIES = [
    "Business purpose",
    "Architecture",
    "Deployment steps",
    "Dependencies",
    "Contacts",
    "Known issues",
    "Maintenance procedures",
    "Future roadmap",
]

GAP_ANALYSIS_SYSTEM_PROMPT = """You are an IT knowledge transfer specialist. You will be given \
combined documentation for a single project (it may be multiple documents concatenated). \
Determine, for each of the following categories, whether the documentation covers it.

Categories:
{categories}

For each category, return one of:
- "present": the category is clearly and substantively covered
- "thin": the category is mentioned but with minimal detail (a sentence or less)
- "missing": the category is not addressed at all

Return ONLY valid JSON in this exact shape, no preamble, no markdown fences:
{{
  "Business purpose": "present" | "thin" | "missing",
  "Architecture": "present" | "thin" | "missing",
  "Deployment steps": "present" | "thin" | "missing",
  "Dependencies": "present" | "thin" | "missing",
  "Contacts": "present" | "thin" | "missing",
  "Known issues": "present" | "thin" | "missing",
  "Maintenance procedures": "present" | "thin" | "missing",
  "Future roadmap": "present" | "thin" | "missing"
}}
"""


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=20))
def analyze_gaps(project_name: str, combined_text: str) -> dict:
    """
    Returns a dict mapping each STANDARD_CATEGORIES entry to 'present' | 'thin' | 'missing'.
    combined_text should be the concatenation of raw_text from all docs tagged
    with this project (truncate before calling if the corpus is very large).
    """
    prompt = GAP_ANALYSIS_SYSTEM_PROMPT.format(categories="\n".join(f"- {c}" for c in STANDARD_CATEGORIES))

    response = get_client().chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": f"Project: {project_name}\n\nDocumentation:\n{combined_text[:20000]}",
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    result = json.loads(response.choices[0].message.content)

    # Defensive normalization in case the model omits a category or uses unexpected casing
    normalized = {}
    for cat in STANDARD_CATEGORIES:
        val = result.get(cat, "missing")
        normalized[cat] = val if val in ("present", "thin", "missing") else "missing"

    return normalized


def missing_and_thin_categories(gap_result: dict) -> list[str]:
    """Convenience helper: returns categories that are 'missing' or 'thin', in checklist order."""
    return [cat for cat in STANDARD_CATEGORIES if gap_result.get(cat) in ("missing", "thin")]


# --- Note on extending this later ---
# If the fixed checklist above turns out to be too rigid (e.g. it misses something
# specific to a niche system), the clustering approach from the earlier pipeline
# design can slot in here as a complementary check: cluster chunk embeddings,
# diff against an expected-topic list, and merge any *additional* gaps it finds
# into this same gap_analysis table. Nothing here needs to be torn out to add that.