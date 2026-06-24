TESTINGGGGG
"""
Step 2: Structured knowledge extraction.

Takes a document's raw text and asks an LLM to extract structured fields
(project, technologies, dependencies, contacts, deployment process, etc.)
as JSON. This runs once per document, on the full text (not per-chunk) --
the categories we care about (deployment process, known issues) are usually
spread across a whole doc, not contained in a single chunk.
"""
import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


EXTRACTION_MODEL = "gpt-4o-mini"  # cheap + good enough for structured extraction

EXTRACTION_SYSTEM_PROMPT = """You are an IT knowledge transfer specialist reviewing internal \
documentation as part of an employee offboarding process. Extract structured information from \
the document below. Return ONLY valid JSON, no preamble, no markdown code fences.

Schema:
{
  "project": string or null,
  "technologies": [string],
  "dependencies": [string],
  "contacts": [string],
  "deployment_process": string or null,
  "known_issues": string or null,
  "future_work": string or null
}

Rules:
- If a field isn't mentioned in the document, use null (or empty array for list fields).
- Do not invent information that isn't in the text.
- "contacts" should be names or roles mentioned as points of contact, not every name in the doc.
- Keep deployment_process / known_issues / future_work as concise summaries (2-4 sentences), \
not verbatim copies.
"""


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=20))
def extract_structured_knowledge(doc_title: str, raw_text: str) -> dict:
    """
    Returns a dict matching the schema above. Truncates very long documents
    to stay within context -- for the MVP, the first ~12k chars is plenty
    for catching project/tech/contact info, which tends to appear early.
    """
    text_for_extraction = raw_text[:12000]

    response = get_client().chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Document title: {doc_title}\n\nDocument text:\n{text_for_extraction}",
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Shouldn't happen with response_format=json_object, but fail loud if it does
        # rather than silently storing garbage.
        raise ValueError(f"Model did not return valid JSON for '{doc_title}': {content[:200]}")
