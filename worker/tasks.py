import asyncio
from worker.celery_app import celery_app
from core.models import SharedContext
from core.pipeline import run_pipeline
from db.models import Job, Report
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost:5432/researchmind")

def _make_session():
    """Create a fresh async engine + session to avoid event loop conflicts in Celery."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    engine = create_async_engine(DATABASE_URL, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False), engine

@celery_app.task(name="worker.tasks.run_research_job")
def run_research_job(job_id: str, topic: str, urls: list):
    """
    Celery task that wraps the async pipeline execution.
    """
    return asyncio.run(_async_run_research_job(job_id, topic, urls))

async def _async_run_research_job(job_id: str, topic: str, urls: list):
    context = SharedContext(
        job_id=job_id,
        topic=topic,
        urls=urls,
        created_at=datetime.utcnow()
    )
    
    # Create fresh DB connections for THIS event loop
    SessionLocal, engine = _make_session()
    
    try:
        # 1. Run the pipeline (all 5 agents)
        completed_context = await run_pipeline(context)
        
        # 2. Persist to Database
        async with SessionLocal() as session:
            job = await session.get(Job, job_id)
            if job:
                job.status = completed_context.status
                job.completed_at = datetime.utcnow()
                if completed_context.plan:
                    job.classification = completed_context.plan.classification
                    
                # Save Final Report if it exists
                if completed_context.final_report:
                    report = Report(
                        job_id=job_id,
                        executive_summary=completed_context.final_report.executive_summary,
                        key_findings=[f.model_dump() for f in completed_context.final_report.key_findings],
                        contradictions_found=completed_context.final_report.contradictions_found,
                        sources_used=completed_context.final_report.sources_used,
                        overall_confidence=completed_context.final_report.overall_confidence
                    )
                    session.add(report)
                    
                await session.commit()
                
    except Exception as e:
        async with SessionLocal() as session:
            job = await session.get(Job, job_id)
            if job:
                job.status = "FAILED"
                job.error_message = str(e)
                await session.commit()
        raise e
    finally:
        await engine.dispose()

