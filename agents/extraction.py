from agents.base import BaseAgent
from core.models import SharedContext, Claim, PipelineEvent
from core.llm_client import generate_json
from datetime import datetime
import uuid


class ExtractionAgent(BaseAgent):
    """
    Extraction Agent — Uses 1 LLM call to extract structured factual claims
    from the raw source content. This turns unstructured web text into 
    clean, verifiable claim objects for the Critique Agent to review.
    """

    async def execute(self, context: SharedContext) -> SharedContext:
        if not context.raw_chunks:
            self.logger.warning("No chunks to extract claims from.")
            return context

        self.logger.info(f"Extracting claims from {len(context.raw_chunks)} source texts...")

        system_prompt = """
        You are a research fact extractor. Carefully read the source materials and extract ALL distinct factual claims.

        Return a JSON object with a single key "claims" containing a list of objects.
        For each claim:
        - "text": the claim stated as one clear, self-contained sentence
        - "source_url": the [Source: ...] URL this claim came from
        - "claim_type": one of FACT, STATISTIC, OPINION, DATE, QUOTE
        - "confidence": 0.0-1.0 (how clearly and reliably this is stated)

        Rules:
        - Only extract what is EXPLICITLY stated in the source text. Never infer or assume.
        - Each claim must be fully self-contained (understandable without reading the source).
        - Include specific details: names, dates, numbers, locations when available.
        - You MUST include the source_url from the [Source: ...] tag for each claim.
        - Extract 15-25 of the most important and interesting claims.
        """

        # ── Build combined source text ──
        combined_parts = []
        for chunk in context.raw_chunks:
            url = self._get_url(chunk.source_id, context.sources)
            combined_parts.append(f"[Source: {url}]\n{chunk.text}")

        combined_text = "\n\n".join(combined_parts)
        word_count = len(combined_text.split())
        self.logger.info(f"Total extraction text: {word_count} words")

        # ── Single LLM call for claim extraction ──
        try:
            result = await generate_json(
                f"TEXT:\n{combined_text}",
                system_prompt,
                model="openai/gpt-oss-20b"
            )
            claims = self._parse_claims(result, context.raw_chunks, context.sources)
            context.claims = claims
            self.logger.info(f"Extracted {len(claims)} structured claims.")
        except Exception as e:
            self.logger.error(f"LLM extraction failed: {e}")
            self.logger.info("Falling back to direct text-based claims...")
            context.claims = self._fallback_claims(context.raw_chunks, context.sources)

        context.events.append(PipelineEvent(
            event_type="AGENT_DONE",
            agent="extraction",
            data={"claims_count": len(context.claims)},
            timestamp=datetime.utcnow()
        ))

        return context

    def _parse_claims(self, result, chunks, sources):
        """Parse LLM JSON into Claim objects with proper source attribution."""
        claims = []
        url_to_chunk = {self._get_url(c.source_id, sources): c for c in chunks}

        for c in result.get("claims", []):
            claimed_url = c.get("source_url", "")
            matched_chunk = url_to_chunk.get(claimed_url, chunks[0])

            claims.append(Claim(
                claim_id=str(uuid.uuid4()),
                text=c.get("text", ""),
                claim_type=c.get("claim_type", "FACT"),
                source_id=matched_chunk.source_id,
                source_url=self._get_url(matched_chunk.source_id, sources),
                chunk_id=matched_chunk.chunk_id,
                confidence=float(c.get("confidence", 0.5))
            ))
        return claims

    def _fallback_claims(self, chunks, sources):
        """If LLM fails, extract first 2 sentences from each chunk as claims."""
        claims = []
        for chunk in chunks:
            url = self._get_url(chunk.source_id, sources)
            sentences = [s.strip() for s in chunk.text.split('.') if len(s.strip()) > 20]
            for sent in sentences[:3]:
                claims.append(Claim(
                    claim_id=str(uuid.uuid4()),
                    text=sent.strip() + '.',
                    claim_type="FACT",
                    source_id=chunk.source_id,
                    source_url=url,
                    chunk_id=chunk.chunk_id,
                    confidence=0.5
                ))
        return claims

    def _get_url(self, source_id, sources):
        for s in sources:
            if s.source_id == source_id:
                return s.url
        return "unknown"
