from fastapi import FastAPI, HTTPException
from typing import Any
from run_ingest import ingest
from run_gap_analysis import analyze_project
from src.db import get_connection
from src.db_writer import get_interview_questions
from pydantic import BaseModel

class QuestionRequest(BaseModel):
    project: str


class UploadRequest(BaseModel):
    sources: list[str]
    sourceDetails: dict[str, Any]
    files: list[Any]
    
app = FastAPI()


@app.get("/")
def home():
    return {"message": "Legacy Loop API running"}

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }

    
@app.get("/questions/{project}")
def get_questions(project: str):
    conn = None
    try:
        conn = get_connection()

        questions = get_interview_questions(conn, project)

        return {
            "success": True,
            "questions": questions
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if conn:
            conn.close()


@app.post("/upload")
def upload(request: UploadRequest):
    try:
        drive = request.sourceDetails["google-drive"]
        folder_link = drive["link"]

        folder_id = folder_link.split("/folders/")[-1]

        stats = ingest(folder_id)
        print(stats)

        project = stats.get("project")
        print(f"Detected project: {project}")

        if project and project != "(none detected)":
            print(f"Running gap analysis for {project}")
            analysis = analyze_project(project)
            print("Gap analysis complete")
        else:
            print("Skipping gap analysis: no project detected")

        return {
            "status": "ok",
            "stats": stats,
            "project": project,
            "gap_analysis": analysis["gap_result"],
            "questions": analysis["questions"],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
    
    
    

