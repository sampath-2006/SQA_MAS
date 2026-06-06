import os
import uuid
import tempfile
import asyncio
import aiosqlite
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from git import Repo

from orchestrator import SQAOrchestrator

app = FastAPI(title="SQA-MAS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = str(Path(__file__).parent / "sqa_state.db")

class ScanRequest(BaseModel):
    github_url: str

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                github_url TEXT,
                status TEXT,
                target_dir TEXT
            )
        ''')
        await db.commit()

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/")
async def root():
    return {"message": "SQA-MAS Backend API is running!"}

async def run_scan_job(job_id: str, github_url: str):
    # 1. Update status to IN_PROGRESS
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jobs SET status = 'IN_PROGRESS' WHERE id = ?", (job_id,))
        await db.commit()
    
    # 2. Clone the repo to a safe temporary directory
    target_dir = tempfile.mkdtemp(prefix="sqa_clone_")
    
    try:
        print(f"[{job_id}] Cloning {github_url} into {target_dir}...")
        Repo.clone_from(github_url, target_dir)
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE jobs SET target_dir = ? WHERE id = ?", (target_dir, job_id))
            await db.commit()
            
        # 3. Run the massive SQA-MAS pipeline!
        print(f"[{job_id}] Triggering orchestrator...")
        orchestrator = SQAOrchestrator(target_dir)
        await orchestrator.run_pipeline()
        
        # 4. Update status to COMPLETED
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE jobs SET status = 'COMPLETED' WHERE id = ?", (job_id,))
            await db.commit()
            
    except Exception as e:
        print(f"[{job_id}] Pipeline failed: {e}")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE jobs SET status = 'FAILED' WHERE id = ?", (job_id,))
            await db.commit()

@app.post("/api/scan")
async def start_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO jobs (id, github_url, status) VALUES (?, ?, ?)", (job_id, request.github_url, "PENDING"))
        await db.commit()
        
    background_tasks.add_task(run_scan_job, job_id, request.github_url)
    
    return {"job_id": job_id, "status": "PENDING"}

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Job not found")
            return {"job_id": job_id, "status": row[0]}

@app.get("/api/report/{job_id}")
async def get_report(job_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status, target_dir FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Job not found")
            status, target_dir = row[0], row[1]
            
    if status != "COMPLETED":
        return {"status": status, "report": None}
        
    report_path = Path(target_dir) / "sqa_report.md"
    if not report_path.exists():
        raise HTTPException(status_code=500, detail="Report file missing after completion")
        
    with open(report_path, "r", encoding="utf-8") as f:
        report_content = f.read()
        
    return {"status": status, "report": report_content}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
