"""
Google Drive ingestion — service account auth.

Uses a service account JSON key file instead of the OAuth Desktop app flow.
This means no browser popup, no cached token file, and no per-user login —
the service account is a machine identity that authenticates silently using
its JSON key.

SETUP REQUIRED:
1. Create a service account in Google Cloud Console (IAM & Admin → Service Accounts)
2. Download its JSON key, save as service_account.json in the project root
3. Share the Drive input folder with the service account's email address
   (found on the service account details page), with Viewer access
4. Share the Drive output folder with the same email, with Editor access
5. Set GOOGLE_SERVICE_ACCOUNT_FILE, DRIVE_FOLDER_ID, and DRIVE_OUTPUT_FOLDER_ID in .env
"""
import io
import os
from typing import Optional
from dotenv import load_dotenv

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader

load_dotenv()

# Read-only scope is sufficient for ingestion.
# The export module (drive_export.py) uses a separate client with write scope.
SCOPES_READ = ["https://www.googleapis.com/auth/drive.readonly"]

# Google native formats get exported to a readable mimetype.
GOOGLE_EXPORT_MAP = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}

SUPPORTED_BINARY_MIMETYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
}


def get_drive_service():
    """
    Build and return a Drive API client authenticated as the service account.
    Silent — no browser, no token cache, no user interaction required.
    """
    service_account_file = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"
    )
    creds = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=SCOPES_READ
    )
    return build("drive", "v3", credentials=creds)


def list_files_in_folder(service, folder_id: str) -> list[dict]:
    """
    List all files directly inside a Drive folder.
    Non-recursive — subfolders won't be traversed automatically.
    See the comment at the bottom of fetch_documents() for how to add recursion.
    """
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
    """
    Return plain text for a Drive file, or None if the type isn't handled yet.
    Supported: Google Docs/Slides/Sheets (native), PDF, plain text, Markdown.
    """
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
        # Skip subfolders — only process actual files
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

    # NOTE: to add subfolder recursion, add this after the loop above:
    # for f in files:
    #     if f["mimeType"] == "application/vnd.google-apps.folder":
    #         documents.extend(fetch_documents_from_folder(service, f["id"]))
    # Then extract fetch_documents_from_folder() as a helper that takes a
    # service object rather than creating a new one each call.