# Offboarding Knowledge Transfer Pipeline

Pulls a departing employee's documentation from Google Drive, extracts
structured knowledge per document, identifies gaps against a standard
knowledge-transfer checklist, generates interview questions for those gaps,
and walks the employee through answering them in a simple Streamlit UI.

## Pipeline

```
Drive docs
    │
    ▼
run_ingest.py        chunk → embed → pgvector, + structured extraction (Step 2)
    │
    ▼
run_gap_analysis.py  gap analysis (Step 3) → question generation (Step 4)
    │
    ▼
app.py (Streamlit)   interview interface (Step 5) → answers saved to Postgres
```

## Setup

1. **Python environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Postgres + pgvector**
   Stand up a Postgres instance with the `vector` extension available, then:
   ```bash
   psql -h <host> -U <user> -d <db> -f schema.sql
   ```

3. **Google Drive OAuth**
   - Create a project in [Google Cloud Console](https://console.cloud.google.com/apis/credentials), enable the Drive API
   - Create OAuth credentials, type **Desktop app**
   - Download the JSON, save as `client_secret.json` in this folder
   - Add yourself as a test user under OAuth consent screen settings (the app is in "testing" mode by default)

4. **Environment variables**
   ```bash
   cp .env.example .env
   ```
   Fill in: `OPENAI_API_KEY`, Postgres connection details, `DRIVE_FOLDER_ID`
   (the ID from the Drive folder's URL, after `/folders/`).

## Usage

**Ingest documents** (run once per batch of new/updated docs):
```bash
python run_ingest.py
```
First run opens a browser window for Drive OAuth consent.

**Run gap analysis + generate questions** for a specific project:
```bash
python run_gap_analysis.py "API Hub Search"
```
The project name should match what shows up in the ingest output
(`-> project: ...`) — it's auto-normalized against fuzzy variants, so close
matches will merge automatically (see console output for any merges).

**Run the interview**:
```bash
streamlit run app.py
```
Opens in your browser. Pick the project, answer the generated questions —
answers save automatically as you go.

## Project structure

```
src/
  drive_ingest.py   Google Drive auth + file listing + text extraction
  embed.py          heading-aware chunking + OpenAI embeddings
  extract.py        Step 2: structured knowledge extraction (LLM)
  gap_analysis.py   Step 3: checklist-based gap detection (LLM)
  questions.py      Step 4: interview question generation (LLM)
  normalize.py      fuzzy-matches project names to avoid duplicate buckets
  db.py             Postgres/pgvector connection
  db_writer.py       all INSERT/UPDATE/SELECT helpers
run_ingest.py        orchestrates Drive -> embed -> extract -> store
run_gap_analysis.py  orchestrates gap analysis -> question generation
app.py               Streamlit interview UI
schema.sql           run once to set up tables
```

## Known limitations (MVP scope)

- Subfolders aren't considered.
- Only runs locally for now.
- Downloads from streamlit as a .txt (pulling directly into drive encounters service quota limitations) 
