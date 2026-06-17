"""
Google Drive ingestion.

First run will open a browser window for OAuth consent (Desktop app flow).
After that, the token is cached in GOOGLE_TOKEN_FILE and reused silently.

Setup required before running:
1. Go to https://console.cloud.google.com/apis/credentials
2. Create a project (or use an existing one), enable the "Google Drive API"
3. Create OAuth client credentials of type "Desktop app"
4. Download the JSON, save it as the path set in GOOGLE_CLIENT_SECRET_FILE
"""
import io
import os
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Native Google formats need to be *exported* to a readable mimetype.
# Binary formats (PDF, etc.) get downloaded as-is and parsed locally.
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
    """Authenticate (interactively on first run) and return a Drive API client."""
    creds = None
    token_file = os.environ["GOOGLE_TOKEN_FILE"]
    secret_file = os.environ["GOOGLE_CLIENT_SECRET_FILE"]

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def list_files_in_folder(service, folder_id: str):
    """List all files in a Drive folder (non-recursive; see note below for subfolders)."""
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

    # NOTE: this only lists files directly inside folder_id. If the corpus has
    # subfolders (e.g. Confluence-style nested spaces exported to Drive), you'll
    # want to recurse: for each file with mimeType
    # 'application/vnd.google-apps.folder', call this function again with its id.


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


from typing import Optional
def extract_text(service, file_meta: dict) -> Optional[str]:
    """
    Return plain text for a Drive file, or None if the type isn't handled yet.
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

    # Unhandled type (images, video, zip, etc.) -- skip for now.
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
