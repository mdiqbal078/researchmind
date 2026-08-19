from agents.base import BaseAgent
from core.models import SharedContext, FinalReport, PipelineEvent
from core.llm_client import generate_completion_stream
from datetime import datetime
import json
import os
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class ReportAgent(BaseAgent):
    """
    Report Agent — Synthesizes critiqued claims and source content into a 
    comprehensive, well-structured research report. Uses 1 streamed LLM call.
    """

    async def execute(self, context: SharedContext) -> SharedContext:
        # ── Handle empty results ──
        if not context.claims and (not context.plan or context.plan.classification != "ADVERSARIAL"):
            self.logger.warning("No claims available for report generation.")
            redis_client = redis.from_url(REDIS_URL)
            msg = "⚠️ **Research Failed:** I was unable to retrieve sufficient information from the web. Please try a different or broader query."
            try:
                await redis_client.publish(f"job:{context.job_id}", json.dumps({"event": "REPORT_CHUNK", "chunk": msg}))
            finally:
                await redis_client.close()

            context.final_report = FinalReport(
                executive_summary=msg,
                key_findings=[],
                contradictions_found=[],
                sources_used=[],
                overall_confidence=0.0,
                generated_at=datetime.utcnow()
            )
            return context

        self.logger.info("Generating Comprehensive Research Report...")

        report_style = context.plan.report_style if context.plan else "balanced"

        # ── Build structured input from critiqued claims ──
        verified_claims = []
        contradicted_claims = []
        unsupported_claims = []
        source_urls = []

        for c in context.claims:
            entry = {"text": c.text, "source_url": c.source_url, "type": c.claim_type}

            if c.source_url not in source_urls:
                source_urls.append(c.source_url)

            if c.critique_status in ("VERIFIED", "UNREVIEWED"):
                verified_claims.append(entry)
            elif c.critique_status == "CONTRADICTED":
                contradicted_claims.append(entry)
            elif c.critique_status in ("UNSUPPORTED", "OUTDATED"):
                unsupported_claims.append(entry)

        # ── Also include raw source content for richer reports ──
        source_context = []
        for s in context.sources:
            chunk_text = ""
            for chunk in context.raw_chunks:
                if chunk.source_id == s.source_id:
                    chunk_text = chunk.text[:500]  # First 500 chars for context
                    break
            source_context.append(f"- **{s.title}** ({s.url}): {chunk_text[:200]}...")

        # ── Adversarial handling ──
        if context.plan and context.plan.classification == "ADVERSARIAL":
            prompt = f"The user asked: '{context.topic}'. Write a polite explanation of why this cannot be objectively researched."
            system_prompt = "You are a research assistant. Respond in Markdown."
        else:
            system_prompt = f"""You are a world-class research analyst. Write a comprehensive, professional research report.

TOPIC: "{context.topic}"
REPORT STYLE: {report_style}
- "confident": State facts directly with authority
- "balanced": Present multiple perspectives fairly  
- "hedged": Use cautious language for uncertain claims

YOUR REPORT MUST INCLUDE ALL OF THESE SECTIONS:

## 📋 Executive Summary
A compelling 3-5 sentence overview of the most important findings.

## 🔍 Key Findings  
The most significant facts discovered, organized with sub-headings. Include specific dates, names, numbers, and quotes. Use bullet points for clarity.

## 📖 Detailed Analysis
Multiple paragraphs of in-depth analysis connecting facts across sources. Provide historical context, significance, and implications. This should be the longest section.

## ⚠️ Contradictions & Limitations
Note any contradicted claims, conflicting information, or gaps in the research. If none, state that sources are consistent.

## 🔗 Sources & References
List each source with its URL and a brief note about what it contributed.

CRITICAL RULES:
- Write AT LEAST 600 words. Be thorough and comprehensive.  
- Use rich Markdown: **bold**, *italics*, bullet points, numbered lists, > blockquotes.
- Cite sources inline using [Source](URL) format throughout the report.
- Synthesize information into flowing, analytical prose — don't just list facts.
- For CONTRADICTED claims, present both perspectives and note the conflict.
- For UNSUPPORTED claims, use hedging language ("reportedly", "according to some sources").
- Include specific facts: dates, names, numbers, locations, quotes."""

            prompt = f"""VERIFIED CLAIMS ({len(verified_claims)} claims):
{json.dumps(verified_claims, indent=1)}

CONTRADICTED CLAIMS ({len(contradicted_claims)} claims):
{json.dumps(contradicted_claims, indent=1)}

UNSUPPORTED/UNCERTAIN CLAIMS ({len(unsupported_claims)} claims):
{json.dumps(unsupported_claims, indent=1)}

SOURCE OVERVIEW:
{chr(10).join(source_context)}"""

        # ── Stream the report via Redis Pub/Sub ──
        redis_client = redis.from_url(REDIS_URL)
        full_report = []

        try:
            async for chunk in generate_completion_stream(prompt, system_prompt, model="llama3-70b-8192"):
                full_report.append(chunk)
                await redis_client.publish(
                    f"job:{context.job_id}",
                    json.dumps({"event": "REPORT_CHUNK", "chunk": chunk})
                )
        finally:
            await redis_client.close()

        markdown_text = "".join(full_report)

        context.final_report = FinalReport(
            executive_summary=markdown_text,
            key_findings=[],
            contradictions_found=[],
            sources_used=source_urls,
            overall_confidence=70.0,
            generated_at=datetime.utcnow()
        )

        context.events.append(PipelineEvent(
            event_type="AGENT_DONE",
            agent="report",
            data={"confidence": context.final_report.overall_confidence},
            timestamp=datetime.utcnow()
        ))

        return context
