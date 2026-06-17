"""
Step 5: Conversational interview interface.

Walks the departing employee through the generated questions, organized by
section (matching the gap categories), rather than free-form chat. Each
section is shown one at a time; answers are saved to Postgres immediately
so nothing is lost if the session is interrupted.

Run with:
    streamlit run app.py
"""
import streamlit as st

from src.db import get_connection
from src.db_writer import get_unanswered_questions, get_all_projects, record_answer

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

    if not questions:
        st.success(f"No open questions for **{project}** — knowledge transfer is complete!")
        return

    # Group remaining questions by category, preserving SECTION_ORDER
    by_category: dict[str, list[dict]] = {}
    for q in questions:
        by_category.setdefault(q["category"], []).append(q)

    ordered_categories = [c for c in SECTION_ORDER if c in by_category]
    # include any categories outside the standard list, just in case
    ordered_categories += [c for c in by_category if c not in SECTION_ORDER]

    total_remaining = len(questions)
    st.progress(0.0, text=f"{total_remaining} question(s) remaining for {project}")

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
