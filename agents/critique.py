from agents.base import BaseAgent
from core.models import SharedContext, CritiqueReport, ClaimReview, Contradiction, PipelineEvent
from core.llm_client import generate_json
from datetime import datetime
import json

class CritiqueAgent(BaseAgent):
    async def execute(self, context: SharedContext) -> SharedContext:
        if not context.plan or not context.plan.run_critique:
            self.logger.info("Critique skipped (SIMPLE_FACT or ADVERSARIAL).")
            # Mark all claims as unreviewed
            for claim in context.claims:
                claim.critique_status = "UNREVIEWED"
                claim.adjusted_confidence = claim.confidence
            return context
            
        if not context.claims:
            return context
            
        self.logger.info(f"Critiquing {len(context.claims)} claims...")
        
        system_prompt = """
        You are a research fact-checker. Review the claims extracted from multiple web sources.

        Return a JSON object with:
        - "claim_reviews": list of objects containing:
            - "claim_id": original ID
            - "status": VERIFIED | CONTRADICTED | UNSUPPORTED | OUTDATED
            - "critique_note": brief explanation
            - "adjusted_confidence": 0.0-1.0
        - "contradictions": list of objects containing:
            - "claim_a_id"
            - "claim_b_id"
            - "explanation"
        - "overall_reliability": 0.0-1.0
        """
        
        # Serialize claims to JSON for the prompt
        claims_data = [{"claim_id": c.claim_id, "text": c.text, "source": c.source_url} for c in context.claims]
        prompt = f"CLAIMS:\n{json.dumps(claims_data, indent=2)}"
        
        # 70B model for heavy reasoning
        result = await generate_json(prompt, system_prompt, model="llama-3.1-70b-versatile")
        
        # Parse results
        reviews = []
        for cr in result.get("claim_reviews", []):
            reviews.append(ClaimReview(
                claim_id=cr["claim_id"],
                status=cr["status"],
                critique_note=cr.get("critique_note", ""),
                adjusted_confidence=float(cr.get("adjusted_confidence", 0.5))
            ))
            
            # Update the original claim object
            for c in context.claims:
                if c.claim_id == cr["claim_id"]:
                    c.critique_status = cr["status"]
                    c.critique_note = cr.get("critique_note", "")
                    c.adjusted_confidence = float(cr.get("adjusted_confidence", 0.5))
                    break
                    
        contradictions = []
        for cd in result.get("contradictions", []):
            contradictions.append(Contradiction(
                claim_a_id=cd["claim_a_id"],
                claim_b_id=cd["claim_b_id"],
                explanation=cd["explanation"]
            ))
            
        context.critique_report = CritiqueReport(
            reviewed_at=datetime.utcnow(),
            claim_reviews=reviews,
            contradictions=contradictions,
            overall_reliability=float(result.get("overall_reliability", 0.5))
        )
        
        context.events.append(PipelineEvent(
            event_type="AGENT_DONE",
            agent="critique",
            data={"contradictions_found": len(contradictions), "reliability": context.critique_report.overall_reliability},
            timestamp=datetime.utcnow()
        ))
        
        return context
