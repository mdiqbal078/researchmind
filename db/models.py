import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from .database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=generate_uuid)
    topic = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    input_urls = Column(ARRAY(String))
    status = Column(String, nullable=False, default="QUEUED")
    current_agent = Column(String)
    classification = Column(String)
    normal_answer = Column(String)
    error_message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    sources = relationship("Source", back_populates="job", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="job", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="job", cascade="all, delete-orphan")

class Source(Base):
    __tablename__ = "sources"
    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"))
    url = Column(String, nullable=False)
    title = Column(String)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    
    job = relationship("Job", back_populates="sources")

class Claim(Base):
    __tablename__ = "claims"
    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"))
    source_id = Column(String, ForeignKey("sources.id"))
    text = Column(String, nullable=False)
    claim_type = Column(String)
    confidence = Column(Float)
    critique_status = Column(String)
    critique_note = Column(String)
    adjusted_confidence = Column(Float)
    
    job = relationship("Job", back_populates="claims")

class Report(Base):
    __tablename__ = "reports"
    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"))
    executive_summary = Column(String, nullable=False)
    key_findings = Column(JSON, nullable=False)
    contradictions_found = Column(JSON)
    sources_used = Column(ARRAY(String))
    overall_confidence = Column(Float)
    generated_at = Column(DateTime, default=datetime.utcnow)
    
    job = relationship("Job", back_populates="reports")
