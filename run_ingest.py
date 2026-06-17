"""
Run the full ingest pipeline: Google Drive -> chunk -> embed -> pgvector.

Usage:
    python run_ingest.py

Requires .env populated (see .env.example) and schema.sql already applied
to your Postgres database.
"""
import os
import sys
from dotenv import load_dotenv

from src.drive_ingest import fetch_documents
from src.embed import chunk_document, embed_chunks
from src.extract import extract_structured_knowledge
from src.normalize import normalize_project_name
from src.db import get_connection
from src.db_writer import (
    upsert_document,
    replace_chunks,
    upsert_structured_knowledge,
    get_all_projects,
)

load_dotenv()


def main():
    folder_id = os.environ.get("DRIVE_FOLDER_ID")
    if not folder_id:
        print("ERROR: set DRIVE_FOLDER_ID in .env to the Drive folder you want to ingest.")
        sys.exit(1)

    print(f"Fetching documents from Drive folder {folder_id} ...")
    documents = fetch_documents(folder_id)
    print(f"\nFound {len(documents)} documents with extractable text.\n")

    if not documents:
        print("Nothing to ingest. Done.")
        return

    conn = get_connection()
    known_projects = get_all_projects(conn)  # fetched once; updated locally as new projects appear

    total_chunks = 0
    for doc in documents:
        print(f"Processing: {doc['title']}")

        doc_id = upsert_document(conn, "google_drive", doc)

        chunks = chunk_document(doc["raw_text"])
        if not chunks:
            print("  (no chunks produced -- skipping embedding)")
            continue

        embeddings = embed_chunks(chunks)
        replace_chunks(conn, doc_id, chunks, embeddings)

        print("  Extracting structured knowledge...")
        extracted = extract_structured_knowledge(doc["title"], doc["raw_text"])

        raw_project = extracted.get("project")
        if raw_project:
            canonical_project, was_merged = normalize_project_name(raw_project, known_projects)
            extracted["project"] = canonical_project
            if not was_merged and canonical_project not in known_projects:
                known_projects.append(canonical_project)

        upsert_structured_knowledge(conn, doc_id, extracted)
        project_label = extracted.get("project") or "(none detected)"
        print(f"  -> project: {project_label}")

        total_chunks += len(chunks)
        print(f"  -> {len(chunks)} chunks embedded and stored")

    conn.close()
    print(f"\nDone. {len(documents)} documents, {total_chunks} chunks total.")


if __name__ == "__main__":
    main()
