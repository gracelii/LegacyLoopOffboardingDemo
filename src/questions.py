"""
Step 4: Generate follow-up interview questions for missing/thin categories.

Organizes questions by section (matching the categories) rather than as one
flat list, so the interview chatbot (Step 5) can walk through them in order:
Project Overview -> Architecture -> Deployment -> Troubleshooting -> Contacts -> Future Work.
"""
import json
from tenacity import retry, stop_after_attempt, wait_exponential

from src.extract import get_client, EXTRACTION_MODEL

QUESTION_GEN_SYSTEM_PROMPT = """You are an IT knowledge transfer specialist preparing for an \
exit interview with a departing employee. You will be given a list of documentation categories \
that are missing or only thinly covered for a specific project. Generate 2-4 specific, concrete \
interview questions per category that would help capture the missing knowledge.

Favor questions that prompt for specifics (names, steps, frequencies, thresholds) over vague \
prompts like "tell me about X". Avoid yes/no questions where possible.

Return ONLY valid JSON in this shape, no preamble, no markdown fences:
{
  "Category Name": ["question 1", "question 2", ...],
  ...
}
"""


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=20))
def generate_questions(project_name: str, missing_categories: list[str]) -> dict[str, list[str]]:
    """
    Returns a dict mapping each category to a list of question strings.
    Only call this with categories that are actually missing/thin --
    don't waste a call generating questions for well-covered areas.
    """
    if not missing_categories:
        return {}

    response = get_client().chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[
            {"role": "system", "content": QUESTION_GEN_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Project: {project_name}\n\n"
                    f"Missing/thin categories:\n" + "\n".join(f"- {c}" for c in missing_categories)
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.3,  # a little variety in question phrasing is fine here
    )

    return json.loads(response.choices[0].message.content)
