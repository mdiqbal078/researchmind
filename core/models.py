from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Dict, Any

class ExecutionPlan(BaseModel):
    classification: str
    reasoning: str
    num_sources: int
    search_queries: List[str]
    run_critique: bool
    report_style: str

class Source(BaseModel):
    source_id: str
    url: str
    title: str
    fetched_at: datetime
    chunk_count: int

class RawChunk(BaseModel):
    chunk_id: str
    source_id: str
    text: str
    position: int

class Claim(BaseModel):
    claim_id: str
    text: str
    claim_type: str
    source_id: str
    source_url: str
    chunk_id: str
    confidence: float
    critique_status: str = "UNREVIEWED"
    critique_note: str = ""
    adjusted_confidence: Optional[float] = None

class ClaimReview(BaseModel):
    claim_id: str
    status: str
    critique_note: str
    adjusted_confidence: float

class Contradiction(BaseModel):
    claim_a_id: str
    claim_b_id: str
    explanation: str

class CritiqueReport(BaseModel):
    reviewed_at: datetime
    claim_reviews: List[ClaimReview]
    contradictions: List[Contradiction]
    overall_reliability: float

class Finding(BaseModel):
    text: str
    source_urls: List[str]
    confidence: float
    status: str

class FinalReport(BaseModel):
    executive_summary: str
    key_findings: List[Finding]
    contradictions_found: List[str]
    sources_used: List[str]
    overall_confidence: float
    generated_at: datetime

class PipelineEvent(BaseModel):
    event_type: str
    agent: Optional[str] = None
    data: Dict[str, Any]
    timestamp: datetime

class SharedContext(BaseModel):
    job_id: str
    topic: str
    urls: List[str] = []
    created_at: datetime
    
    plan: Optional[ExecutionPlan] = None
    sources: List[Source] = []
    raw_chunks: List[RawChunk] = []
    claims: List[Claim] = []
    critique_report: Optional[CritiqueReport] = None
    final_report: Optional[FinalReport] = None
    
    status: str = "QUEUED"
    current_agent: Optional[str] = None
    events: List[PipelineEvent] = []
    errors: List[str] = []
