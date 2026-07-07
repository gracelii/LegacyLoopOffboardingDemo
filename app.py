"""
Step 5: Conversational interview interface + Drive export.

Walks the departing employee through the generated questions, organized by
section (matching the gap categories), rather than free-form chat. Each
section is shown one at a time; answers are saved to Postgres immediately
so nothing is lost if the session is interrupted.

When all questions are answered, a "Export to Google Drive" button appears
that writes a formatted summary doc to the designated output folder and
returns a direct link.

Run with:
    streamlit run app.py
"""
import os
from datetime import date
import streamlit as st
from dotenv import load_dotenv

from src.db import get_connection
from src.db_writer import get_unanswered_questions, get_all_projects, record_answer

load_dotenv()

st.set_page_config(page_title="Knowledge Transfer Interview", page_icon="📋")

# Section order matches the categories in gap_analysis.py / questions.py
SECTION_ORDER = [
    "Business purpose",
    "Architecture",
    "Deployment steps",
    "Dependencies",
    "Contacts",
    "Known issues",
    "Maintenance procedures",
    "Future roadmap",
]


@st.cache_resource
def get_db_connection():
    return get_connection()


def get_answered_questions(conn, project: str) -> list[dict]:
    """Fetch all answered questions for a project, for the Drive export."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT category, question_text, answer_text
            FROM interview_questions
            WHERE project = %s AND answer_text IS NOT NULL
            ORDER BY category, created_at;
            """,
            (project,),
        )
        rows = cur.fetchall()
    return [{"category": r[0], "question_text": r[1], "answer_text": r[2]} for r in rows]


def main():
    st.title("📋 Knowledge Transfer Interview")
    st.caption("Answers are saved automatically as you go — you can close this and come back.")

    conn = get_db_connection()
    projects = get_all_projects(conn)

    if not projects:
        st.warning(
            "No projects found yet. Run `run_ingest.py` to ingest documents, "
            "then `run_gap_analysis.py \"Project Name\"` to generate questions."
        )
        return

    project = st.selectbox("Project", projects)
    questions = get_unanswered_questions(conn, project)

    # --- All questions answered: show completion state + download button ---
    if not questions:
        st.success(f"✅ All questions answered for **{project}** — knowledge transfer is complete!")

        answered = get_answered_questions(conn, project)
        if answered:
            from src.drive_export import _build_text_content
            summary_text = _build_text_content(project, answered)
            filename = f"knowledge-transfer-{project.lower().replace(' ', '-')}-{date.today().strftime('%Y-%m-%d')}.txt"

            st.markdown(f"**{len(answered)} answers captured.** Download the summary below.")
            st.download_button(
                label="📄 Download Knowledge Transfer Summary",
                data=summary_text.encode("utf-8"),
                file_name=filename,
                mime="text/plain",
            )
        return

    # --- Questions remaining: show interview UI ---
    total_remaining = len(questions)

    # Count total questions (answered + unanswered) to show a real progress bar
    answered_count = len(get_answered_questions(conn, project))
    total_count = answered_count + total_remaining
    progress = answered_count / total_count if total_count > 0 else 0
    st.progress(progress, text=f"{total_remaining} question(s) remaining for {project}")

    # Group remaining questions by category, preserving SECTION_ORDER
    by_category: dict[str, list[dict]] = {}
    for q in questions:
        by_category.setdefault(q["category"], []).append(q)

    ordered_categories = [c for c in SECTION_ORDER if c in by_category]
    ordered_categories += [c for c in by_category if c not in SECTION_ORDER]

    for category in ordered_categories:
        st.subheader(category)
        for q in by_category[category]:
            answer = st.text_area(q["question_text"], key=f"q_{q['question_id']}", height=80)
            if st.button("Save answer", key=f"save_{q['question_id']}"):
                if answer.strip():
                    record_answer(conn, q["question_id"], answer.strip())
                    st.success("Saved.")
                    st.rerun()
                else:
                    st.error("Answer can't be empty.")
        st.divider()


if __name__ == "__main__":
    main()