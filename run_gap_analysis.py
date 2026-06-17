"""
Run Steps 3-4: gap analysis + interview question generation, for one project.

Usage:
    python run_gap_analysis.py "API Hub Search"

Run this after run_ingest.py has populated structured_knowledge for the
relevant documents (i.e. after their "project" field has been extracted).
"""
import sys

from src.db import get_connection
from src.gap_analysis import analyze_gaps, missing_and_thin_categories
from src.questions import generate_questions
from src.db_writer import (
    get_documents_for_project,
    upsert_gap_analysis,
    insert_interview_questions,
)


def main():
    if len(sys.argv) < 2:
        print('Usage: python run_gap_analysis.py "Project Name"')
        sys.exit(1)

    project = sys.argv[1]
    conn = get_connection()

    docs = get_documents_for_project(conn, project)
    if not docs:
        print(f"No documents found tagged with project '{project}'.")
        print("Check that run_ingest.py has run and extracted a matching project name.")
        sys.exit(1)

    print(f"Found {len(docs)} documents for project '{project}':")
    for d in docs:
        print(f"  - {d['title']}")

    combined_text = "\n\n---\n\n".join(d["raw_text"] for d in docs)
    doc_ids = [d["doc_id"] for d in docs]

    print("\nRunning gap analysis...")
    gap_result = analyze_gaps(project, combined_text)
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
    questions = generate_questions(project, gaps)
    insert_interview_questions(conn, project, questions)

    print("\nGenerated questions:")
    for category, qs in questions.items():
        print(f"\n  {category}:")
        for q in qs:
            print(f"    - {q}")

    conn.close()
    print(f"\nDone. Run the Streamlit app to conduct the interview for '{project}'.")


if __name__ == "__main__":
    main()
