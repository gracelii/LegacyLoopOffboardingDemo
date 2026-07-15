"""
Drive export — write completed interview summaries back to Google Drive.
Uses the credentials helper (Streamlit secrets in prod, file in dev).
"""
import io
import os
from datetime import date
from typing import Optional
from dotenv import load_dotenv

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from src.credentials import get_credentials

load_dotenv()

SCOPES_WRITE = ["https://www.googleapis.com/auth/drive"]

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


def _get_drive_service_write():
    creds = get_credentials(SCOPES_WRITE)
    return build("drive", "v3", credentials=creds)


def _build_text_content(project: str, answered_questions: list[dict]) -> str:
    """Build a plain text summary of the interview answers."""
    lines = []
    lines.append(f"KNOWLEDGE TRANSFER: {project.upper()}")
    lines.append(f"Date: {date.today().strftime('%B %d, %Y')}")
    lines.append("=" * 60)
    lines.append("")

    by_category: dict[str, list[dict]] = {}
    for q in answered_questions:
        by_category.setdefault(q["category"], []).append(q)

    ordered_categories = [c for c in SECTION_ORDER if c in by_category]
    ordered_categories += [c for c in by_category if c not in SECTION_ORDER]

    for category in ordered_categories:
        lines.append(f"\n{category.upper()}")
        lines.append("-" * len(category))
        for q in by_category[category]:
            lines.append(f"\nQ: {q['question_text']}")
            lines.append(f"A: {q['answer_text'] or '(no answer provided)'}")

    return "\n".join(lines)


def export_to_drive(
    project: str,
    answered_questions: list[dict],
    output_folder_id: Optional[str] = None,
) -> str:
    """Upload a plain text interview summary to the output Drive folder."""
    folder_id = output_folder_id or os.environ.get("DRIVE_OUTPUT_FOLDER_ID")
    if not folder_id:
        raise ValueError("DRIVE_OUTPUT_FOLDER_ID not set.")

    drive_service = _get_drive_service_write()
    doc_title = f"Knowledge Transfer — {project} ({date.today().strftime('%Y-%m-%d')}).txt"
    content = _build_text_content(project, answered_questions)
    content_bytes = content.encode("utf-8")

    file_metadata = {"name": doc_title, "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(content_bytes), mimetype="text/plain", resumable=False
    )
    created_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
        supportsAllDrives=True,
    ).execute()

    return created_file.get("webViewLink") or \
        f"https://drive.google.com/file/d/{created_file['id']}/view"