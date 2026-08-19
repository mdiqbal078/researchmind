# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession
# pyrefly: ignore [missing-import]
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
import asyncio
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as redis

from db.database import get_db
from db.models import Job, Report
from core.llm_client import generate_completion, generate_completion_stream
from worker.tasks import run_research_job
from db.database import AsyncSessionLocal
import os
import json

router = APIRouter()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class QueryRequest(BaseModel):
    query: str
    mode: str = "auto" # normal | research | auto
    urls: List[str] = []

@router.post("/query")
async def create_query(request: QueryRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    mode = request.mode
    
    # Auto Mode Classification
    if mode == "auto":
        prompt = f"Does this query require multi-source internet research, or is it a simple fact answerable in one sentence? Query: '{request.query}'. Answer strictly with 'RESEARCH' or 'NORMAL'."
        try:
            resp = await generate_completion(prompt, model="qwen/qwen3.6-27b")
            mode = "research" if "RESEARCH" in resp.upper() else "normal"
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Create Job in DB
    job = Job(topic=request.query, mode=mode, input_urls=request.urls)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    if mode == "normal":
        # Normal Mode: Stream via Background Task
        job.status = "QUEUED"
        await db.commit()
        
        async def stream_normal_answer(job_id: str, query: str):
            redis_client = redis.from_url(REDIS_URL)
            await redis_client.publish(f"job:{job_id}", json.dumps({"event": "STATUS_CHANGE", "status": "Synthesizing answer..."}))
            
            full_answer = []
            try:
                async for chunk in generate_completion_stream(query, model="qwen/qwen3.6-27b"):
                    full_answer.append(chunk)
                    await redis_client.publish(f"job:{job_id}", json.dumps({"event": "REPORT_CHUNK", "chunk": chunk}))
                
                # Save to DB
                async with AsyncSessionLocal() as session:
                    db_job = await session.get(Job, job_id)
                    if db_job:
                        db_job.status = "COMPLETED"
                        db_job.normal_answer = "".join(full_answer)
                        await session.commit()
                        
                await redis_client.publish(f"job:{job_id}", json.dumps({"event": "COMPLETE"}))
            except Exception as e:
                await redis_client.publish(f"job:{job_id}", json.dumps({"event": "ERROR", "message": str(e)}))
            finally:
                await redis_client.close()

        background_tasks.add_task(stream_normal_answer, job.id, request.query)
        
        return {
            "job_id": job.id, 
            "mode": "normal", 
            "status": "QUEUED",
            "message": "Stream started. Track at /stream/{job_id}"
        }
        
    else:
        # Research Mode: Enqueue Celery Task
        run_research_job.delay(str(job.id), request.query, request.urls)
        return {
            "job_id": job.id, 
            "mode": "research", 
            "status": "QUEUED",
            "message": "Research pipeline started. Track at /status/{job_id} or /stream/{job_id}"
        }

@router.get("/status/{job_id}")
async def get_status(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job.id, "status": job.status, "classification": job.classification}

@router.get("/result/{job_id}")
async def get_result(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.mode == "normal":
        return {"job_id": job.id, "mode": "normal", "answer": job.normal_answer}
        
    result = await db.execute(select(Report).where(Report.job_id == job_id))
    report = result.scalars().first()
    
    if not report:
        return {"job_id": job.id, "status": job.status, "message": "Report not yet generated or failed"}
        
    return {
        "job_id": job.id,
        "mode": "research",
        "report": {
            "executive_summary": report.executive_summary,
            "key_findings": report.key_findings,
            "contradictions_found": report.contradictions_found,
            "sources_used": report.sources_used,
            "overall_confidence": report.overall_confidence
        }
    }

@router.get("/stream/{job_id}")
async def stream_progress(job_id: str, request: Request):
    """SSE endpoint to stream pipeline progress from Redis Pub/Sub."""
    async def event_generator():
        redis_client = redis.from_url(REDIS_URL)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"job:{job_id}")
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data = message["data"].decode("utf-8")
                    yield {"data": data}
                    if "COMPLETE" in data or "ERROR" in data:
                        break
        finally:
            await pubsub.unsubscribe(f"job:{job_id}")
            await redis_client.close()
            
    return EventSourceResponse(event_generator())

@router.get("/jobs")
async def list_jobs(db: AsyncSession = Depends(get_db)):
    """Returns the latest 10 research queries/jobs."""
    result = await db.execute(select(Job).order_by(Job.created_at.desc()).limit(10))
    jobs = result.scalars().all()
    return [{
        "id": j.id,
        "topic": j.topic,
        "mode": j.mode,
        "status": j.status,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "classification": j.classification
    } for j in jobs]
