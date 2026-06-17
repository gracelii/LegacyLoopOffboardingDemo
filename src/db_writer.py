"""
Writes documents + chunks + embeddings into Postgres/pgvector.

Swap point: replacing this module with a ChromaDB equivalent is the only
change needed to switch storage backends -- callers (run_ingest.py) don't
need to know which store is underneath.
"""
from src.db import get_connection
import json


def upsert_document(conn, source_system: str, doc: dict) -> str:
    """
    Insert or update a document row. Returns the doc_id (as a string).
    On conflict (same source_system + source_id), refreshes metadata and text
    but the caller is responsible for deleting old chunks first if re-ingesting.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents
                (source_system, source_id, title, mime_type, author, last_modified, url, raw_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_system, source_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                mime_type = EXCLUDED.mime_type,
                author = EXCLUDED.author,
                last_modified = EXCLUDED.last_modified,
                url = EXCLUDED.url,
                raw_text = EXCLUDED.raw_text,
                ingested_at = now()
            RETURNING doc_id;
            """,
            (
                source_system,
                doc["source_id"],
                doc["title"],
                doc.get("mime_type"),
                doc.get("author"),
                doc.get("last_modified"),
                doc.get("url"),
                doc["raw_text"],
            ),
        )
        doc_id = cur.fetchone()[0]
    conn.commit()
    return doc_id


def replace_chunks(conn, doc_id: str, chunks: list[str], embeddings: list[list[float]]):
    """Delete any existing chunks for this doc, then insert the fresh set."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE doc_id = %s;", (doc_id,))
        for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            cur.execute(
                """
                INSERT INTO chunks (doc_id, chunk_index, chunk_text, token_count, embedding)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (doc_id, idx, chunk_text, len(chunk_text.split()), embedding),
            )
    conn.commit()


def upsert_structured_knowledge(conn, doc_id: str, extracted: dict):
    """Store the Step 2 LLM extraction for a document."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO structured_knowledge
                (doc_id, project, technologies, dependencies, contacts,
                 deployment_process, known_issues, future_work, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doc_id)
            DO UPDATE SET
                project = EXCLUDED.project,
                technologies = EXCLUDED.technologies,
                dependencies = EXCLUDED.dependencies,
                contacts = EXCLUDED.contacts,
                deployment_process = EXCLUDED.deployment_process,
                known_issues = EXCLUDED.known_issues,
                future_work = EXCLUDED.future_work,
                raw_json = EXCLUDED.raw_json,
                extracted_at = now();
            """,
            (
                doc_id,
                extracted.get("project"),
                extracted.get("technologies") or [],
                extracted.get("dependencies") or [],
                extracted.get("contacts") or [],
                extracted.get("deployment_process"),
                extracted.get("known_issues"),
                extracted.get("future_work"),
                json.dumps(extracted),
            ),
        )
    conn.commit()


def upsert_gap_analysis(conn, project: str, gap_result: dict, evidence_doc_ids: list[str]):
    """Store the Step 3 gap analysis, one row per category, for a project."""
    with conn.cursor() as cur:
        for category, status in gap_result.items():
            cur.execute(
                """
                INSERT INTO gap_analysis (project, category, status, evidence_doc_ids)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (project, category)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    evidence_doc_ids = EXCLUDED.evidence_doc_ids,
                    analyzed_at = now();
                """,
                (project, category, status, evidence_doc_ids),
            )
    conn.commit()


def insert_interview_questions(conn, project: str, questions_by_category: dict[str, list[str]]):
    """Store the Step 4 generated questions, skipping ones already stored verbatim."""
    with conn.cursor() as cur:
        for category, questions in questions_by_category.items():
            for q_text in questions:
                cur.execute(
                    """
                    INSERT INTO interview_questions (project, category, question_text)
                    SELECT %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM interview_questions
                        WHERE project = %s AND category = %s AND question_text = %s
                    );
                    """,
                    (project, category, q_text, project, category, q_text),
                )
    conn.commit()


def record_answer(conn, question_id: str, answer_text: str):
    """Store an interview answer (Step 5)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE interview_questions
            SET answer_text = %s, answered_at = now()
            WHERE question_id = %s;
            """,
            (answer_text, question_id),
        )
    conn.commit()


def get_unanswered_questions(conn, project: str) -> list[dict]:
    """Fetch all not-yet-answered questions for a project, grouped logically by category order."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT question_id, category, question_text
            FROM interview_questions
            WHERE project = %s AND answer_text IS NULL
            ORDER BY category, created_at;
            """,
            (project,),
        )
        rows = cur.fetchall()
    return [{"question_id": r[0], "category": r[1], "question_text": r[2]} for r in rows]


def get_documents_for_project(conn, project: str) -> list[dict]:
    """Fetch raw_text + doc_id for all documents tagged with a given project."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.doc_id, d.title, d.raw_text
            FROM documents d
            JOIN structured_knowledge sk ON sk.doc_id = d.doc_id
            WHERE sk.project = %s;
            """,
            (project,),
        )
        rows = cur.fetchall()
    return [{"doc_id": r[0], "title": r[1], "raw_text": r[2]} for r in rows]


def get_all_projects(conn) -> list[str]:
    """Distinct project names seen so far, for populating a dropdown in the UI."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT project FROM structured_knowledge WHERE project IS NOT NULL ORDER BY project;"
        )
        return [r[0] for r in cur.fetchall()]
