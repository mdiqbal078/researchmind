from core.models import SharedContext, PipelineEvent
from agents.orchestrator import OrchestratorAgent
from agents.retrieval import RetrievalAgent
from agents.extraction import ExtractionAgent
from agents.critique import CritiqueAgent
from agents.report import ReportAgent
from datetime import datetime
import asyncio
import redis.asyncio as redis
import json
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

async def run_pipeline(context: SharedContext):
    """
    Executes the linear 5-agent pipeline.
    Publishes events to Redis Pub/Sub for SSE streaming.
    """
    # Create a FRESH Redis client per pipeline run to avoid event loop conflicts
    redis_client = redis.from_url(REDIS_URL)
    
    agents = [
        ("orchestrator", OrchestratorAgent()),
        ("retrieval", RetrievalAgent()),
        ("extraction", ExtractionAgent()),
        ("critique", CritiqueAgent()),
        ("report", ReportAgent())
    ]
    
    context.status = "RUNNING"
    await _publish_event(redis_client, context.job_id, {"event": "STATUS_CHANGE", "status": "RUNNING"})
    
    try:
        for name, agent in agents:
            context.current_agent = name
            await _publish_event(redis_client, context.job_id, {"event": "AGENT_START", "agent": name, "timestamp": datetime.utcnow().isoformat()})
            
            # Execute the agent
            context = await agent.execute(context)
            
            # Publish the AGENT_DONE event that the agent added
            if context.events and context.events[-1].agent == name:
                event = context.events[-1]
                await _publish_event(redis_client, context.job_id, {
                    "event": event.event_type,
                    "agent": event.agent,
                    "data": event.data,
                    "timestamp": event.timestamp.isoformat()
                })
                
            # Short-circuit if adversarial or empty
            if name == "orchestrator" and context.plan and context.plan.classification == "ADVERSARIAL":
                break # Skip to report
                
        context.status = "COMPLETED"
        context.current_agent = None
        
        if context.final_report:
            await _publish_event(redis_client, context.job_id, {
                "event": "COMPLETE",
                "overall_confidence": context.final_report.overall_confidence
            })
            
    except Exception as e:
        context.status = "FAILED"
        context.errors.append(str(e))
        await _publish_event(redis_client, context.job_id, {"event": "ERROR", "message": str(e)})
        raise e
    finally:
        await redis_client.close()
        
    return context

async def _publish_event(redis_client, job_id: str, data: dict):
    channel = f"job:{job_id}"
    await redis_client.publish(channel, json.dumps(data))

