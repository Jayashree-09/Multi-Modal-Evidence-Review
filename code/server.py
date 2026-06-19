"""
VerifiClaim AI — FastAPI Backend Server
Serves the React frontend and provides API endpoints for claim verification.
"""

import os
import sys
import csv
import json
import shutil
import uuid
import logging
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

# Add parent directory to path so we can import main verifier
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="VerifiClaim AI", version="1.0.0")

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for evaluation history
evaluation_history = []

# Paths
BASE_DIR = Path(__file__).parent.parent
DATASET_DIR = BASE_DIR / "dataset"
UPLOAD_DIR = BASE_DIR / "dataset" / "images" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Serve images folder statically so frontend can display them
app.mount("/images", StaticFiles(directory=str(DATASET_DIR / "images")), name="images")


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_user_history():
    path = DATASET_DIR / "user_history.csv"
    if path.exists():
        rows = load_csv(str(path))
        return {r["user_id"]: r for r in rows}
    return {}


def load_evidence_requirements():
    path = DATASET_DIR / "evidence_requirements.csv"
    if path.exists():
        return load_csv(str(path))
    return []


# ─── Authentication (mock) ───────────────────────────────────────────
USERS = {
    "admin": {"password": "admin", "role": "Admin"},
    "reviewer": {"password": "reviewer", "role": "Reviewer"},
}


@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = USERS.get(username)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {
        "success": True,
        "user": {"username": username, "role": user["role"]},
        "token": str(uuid.uuid4()),
    }


# ─── Claim Verification ─────────────────────────────────────────────
@app.post("/api/verify")
async def verify_claim(
    user_id: str = Form(...),
    claim_object: str = Form(...),
    user_claim: str = Form(...),
    images: list[UploadFile] = File(...),
    x_gemini_api_key: str = Header(None, alias="X-Gemini-API-Key"),
):
    """Process a single claim with uploaded images."""
    api_key = x_gemini_api_key or os.environ.get("GEMINI_API_KEY")

    # Save uploaded images to temp directory
    case_id = f"case_upload_{uuid.uuid4().hex[:8]}"
    case_dir = UPLOAD_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    image_paths = []
    for i, img in enumerate(images, 1):
         ext = Path(img.filename).suffix or ".jpg"
         fname = f"img_{i}{ext}"
         fpath = case_dir / fname
         with open(fpath, "wb") as f:
             content = await img.read()
             f.write(content)
         image_paths.append(f"images/uploads/{case_id}/{fname}")

    # Build a row like claims.csv
    row = {
        "user_id": user_id,
        "image_paths": ";".join(image_paths),
        "user_claim": user_claim,
        "claim_object": claim_object,
    }

    # Import and run verifier
    try:
        import main as verifier
        import google.generativeai as genai

        model = None
        if api_key:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(verifier.MODEL)
            except Exception as e:
                log.error("Failed to configure Gemini API in server: %s", e)
                model = None

        user_history = load_user_history()
        evidence_reqs = load_evidence_requirements()
        sample_lookup = verifier.load_sample_claims_lookup(str(DATASET_DIR))

        result = verifier.process_row(
            model, row, str(DATASET_DIR), user_history, evidence_reqs, sample_lookup
        )

        # Add metadata
        result["id"] = str(uuid.uuid4())
        result["timestamp"] = datetime.now().isoformat()
        result["case_id"] = case_id

        evaluation_history.insert(0, result)

        return JSONResponse(content=result)

    except Exception as e:
        log.error("Verification failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─── History ─────────────────────────────────────────────────────────
@app.get("/api/history")
async def get_history():
    return evaluation_history


@app.get("/api/history/{claim_id}")
async def get_claim_detail(claim_id: str):
    for item in evaluation_history:
        if item.get("id") == claim_id:
            return item
    raise HTTPException(status_code=404, detail="Claim not found")


# ─── User History ────────────────────────────────────────────────────
@app.get("/api/user-history")
async def get_user_history():
    return load_user_history()


@app.get("/api/user-history/{user_id}")
async def get_user_history_detail(user_id: str):
    history = load_user_history()
    if user_id in history:
        return history[user_id]
    raise HTTPException(status_code=404, detail="User not found")


# ─── Evidence Requirements ───────────────────────────────────────────
@app.get("/api/evidence-requirements")
async def get_evidence_requirements():
    return load_evidence_requirements()


# ─── Batch Processing ────────────────────────────────────────────────
@app.post("/api/batch-verify")
async def batch_verify(x_gemini_api_key: str = Header(None, alias="X-Gemini-API-Key")):
    """Run verification on all claims in claims.csv and produce output.csv."""
    api_key = x_gemini_api_key or os.environ.get("GEMINI_API_KEY")

    try:
        import main as verifier

        results = verifier.run(
            dataset_dir=str(DATASET_DIR),
            input_csv=str(DATASET_DIR / "claims.csv"),
            output_csv=str(BASE_DIR / "output.csv"),
            api_key=api_key,
        )
        return {
            "success": True,
            "rows_processed": len(results),
            "output_file": "output.csv",
        }
    except Exception as e:
        log.error("Batch verification failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Evaluation ──────────────────────────────────────────────────────
@app.post("/api/evaluate")
async def run_evaluation(x_gemini_api_key: str = Header(None, alias="X-Gemini-API-Key")):
    """Run evaluation on sample_claims.csv."""
    api_key = x_gemini_api_key or os.environ.get("GEMINI_API_KEY")

    try:
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key

        sys.path.insert(0, str(Path(__file__).parent / "evaluation"))
        import evaluate

        evaluate.run_evaluation(str(DATASET_DIR))

        scores_path = Path(__file__).parent / "evaluation" / "scores.json"
        if scores_path.exists():
            with open(scores_path) as f:
                scores = json.load(f)
            return {"success": True, "scores": scores}
        return {"success": True, "message": "Evaluation complete. Check evaluation_report.md"}
    except Exception as e:
        log.error("Evaluation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Static files (production build) ────────────────────────────────
frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
