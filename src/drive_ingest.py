"""
Google Drive ingestion — service account auth.

Uses a service account credential (from Streamlit secrets in production,
or from a local JSON file in development). See src/credentials.py for
how credentials are loaded.

SETUP REQUIRED:
1. Create a service account in Google Cloud Console (IAM & Admin → Service Accounts)
2. Share the Drive input folder with the service account email (Viewer access)
3. For local dev: save the JSON key as service_account.json, set
   GOOGLE_SERVICE_ACCOUNT_FILE in .env
4. For Streamlit deployment: paste the JSON contents as GOOGLE_SERVICE_ACCOUNT_JSON
   in Streamlit Cloud secrets
"""
import io
import os
from typing import Optional
from dotenv import load_dotenv

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader

from src.credentials import get_credentials

load_dotenv()

SCOPES_READ = ["https://www.googleapis.com/auth/drive.readonly"]

GOOGLE_EXPORT_MAP = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}


def get_drive_service():
    """Build and return a Drive API client authenticated as the service account."""
    creds = get_credentials(SCOPES_READ)
    return build("drive", "v3", credentials=creds)


def list_files_in_folder(service, folder_id: str) -> list[dict]:
    """List all files directly inside a Drive folder. Non-recursive."""
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"

    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, owners)",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return files


def _download_binary(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _export_google_native(service, file_id: str, export_mime: str) -> bytes:
    request = service.files().export_media(fileId=file_id, mimeType=export_mime)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def extract_text(service, file_meta: dict) -> Optional[str]:
    """Return plain text for a Drive file, or None if the type isn't handled."""
    mime_type = file_meta["mimeType"]
    file_id = file_meta["id"]

    if mime_type in GOOGLE_EXPORT_MAP:
        raw = _export_google_native(service, file_id, GOOGLE_EXPORT_MAP[mime_type])
        return raw.decode("utf-8", errors="replace")

    if mime_type == "application/pdf":
        raw = _download_binary(service, file_id)
        reader = PdfReader(io.BytesIO(raw))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    if mime_type in ("text/plain", "text/markdown"):
        raw = _download_binary(service, file_id)
        return raw.decode("utf-8", errors="replace")

    return None


def fetch_documents(folder_id: str) -> list[dict]:
    """
    Top-level entry point: returns a list of dicts ready for the embedding stage.
    Each dict: {source_id, title, mime_type, author, last_modified, url, raw_text}
    """
    service = get_drive_service()
    files = list_files_in_folder(service, folder_id)

    documents = []
    for f in files:
        if f["mimeType"] == "application/vnd.google-apps.folder":
            continue

        text = extract_text(service, f)
        if not text or not text.strip():
            print(f"  [skip] {f['name']} ({f['mimeType']}) -- no extractable text")
            continue

        owners = f.get("owners", [])
        author = owners[0]["displayName"] if owners else None

        documents.append(
            {
                "source_id": f["id"],
                "title": f["name"],
                "mime_type": f["mimeType"],
                "author": author,
                "last_modified": f.get("modifiedTime"),
                "url": f"https://drive.google.com/file/d/{f['id']}/view",
                "raw_text": text,
            }
        )
        print(f"  [ok]   {f['name']} -- {len(text)} chars extracted")

    return documents