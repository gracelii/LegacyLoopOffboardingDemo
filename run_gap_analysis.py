"""
Run Steps 3-4: gap analysis + interview question generation, for one project.

Usage:
    python run_gap_analysis.py "API Hub Search"

Run this after run_ingest.py has populated structured_knowledge for the
relevant documents (i.e. after their "project" field has been extracted).
"""
import sys
import logging

from src.db import get_connection
from src.gap_analysis import analyze_gaps, missing_and_thin_categories, STANDARD_CATEGORIES
from src.questions import generate_questions
from src.db_writer import (
    get_documents_for_project,
    upsert_gap_analysis,
    insert_interview_questions,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def analyze_project(project):
    if not project:
        raise ValueError("Project name is required.")

    conn = get_connection()

    docs = get_documents_for_project(conn, project)
    if not docs:
        raise ValueError(f"No documents found for project '{project}'")

    print(f"Found {len(docs)} documents for project '{project}':")
    for d in docs:
        print(f"  - {d['title']}")

    combined_text = "\n\n---\n\n".join(d["raw_text"] for d in docs)
    doc_ids = [d["doc_id"] for d in docs]

    print("\nRunning gap analysis...")
    gap_result = analyze_gaps(project, combined_text)

    # If the API failed, analyze_gaps returns a safe fallback (all missing).
    # Detect this and warn clearly rather than silently storing misleading data.
    all_missing = all(v == "missing" for v in gap_result.values())
    if all_missing and len(gap_result) == len(STANDARD_CATEGORIES):
        print(
            "\n⚠️  Warning: gap analysis returned all-missing — this may indicate "
            "an API error (timeout or quota issue) rather than a genuine result. "
            "Check the logs above. Proceeding with question generation, but results "
            "may not reflect the actual document content."
        )

    upsert_gap_analysis(conn, project, gap_result, doc_ids)

    print("\nCoverage:")
    for category, status in gap_result.items():
        marker = {"present": "[OK]   ", "thin": "[THIN] ", "missing": "[GAP]  "}[status]
        print(f"  {marker}{category}")

    gaps = missing_and_thin_categories(gap_result)
    if not gaps:
        print("\nNo gaps found -- nothing to generate questions for.")
        conn.close()
        return

    print(f"\nGenerating interview questions for {len(gaps)} categories...")
    try:
        questions = generate_questions(project, gaps)
    except Exception as e:
        conn.close()
        raise RuntimeError(f"Question generation failed: {e}")

    insert_interview_questions(conn, project, questions)

    print("\nGenerated questions:")
    for category, qs in questions.items():
        print(f"\n  {category}:")
        for q in qs:
            print(f"    - {q}")

    conn.close()
    if not gaps:
        conn.close()
        return {
            "gap_result": gap_result,
            "questions": {},
        }

    return {
        "gap_result": gap_result,
        "questions": questions,
    }




if __name__ == "__main__":
    analyze_project(sys.argv[1])