from agents.base import BaseAgent
from core.models import SharedContext, ExecutionPlan, PipelineEvent
from core.llm_client import generate_json
from datetime import datetime

class OrchestratorAgent(BaseAgent):
    async def execute(self, context: SharedContext) -> SharedContext:
        self.logger.info(f"Orchestrator analyzing query: {context.topic}")
        
        system_prompt = """
        You are a research query planner. Analyze the user's query and create an execution plan for a multi-agent research pipeline.

        Classify the query into exactly one category:
        - SIMPLE_FACT: Well-documented, single-answer topic.
        - MULTI_SOURCE: Needs multiple sources for a complete picture.
        - CONTROVERSIAL: Sources likely disagree.
        - ADVERSARIAL: False premise, fictional, future event, or dangerous.

        Return a JSON execution plan with these keys:
        - "classification" (string)
        - "reasoning" (string)
        - "num_sources" (int: 3 for SIMPLE_FACT, 5 for MULTI, 6-7 for CONTROVERSIAL, 0 for ADVERSARIAL)
        - "search_queries" (list of strings: 2-3 diverse search queries)
        - "run_critique" (bool: false for SIMPLE_FACT and ADVERSARIAL, true otherwise)
        - "report_style" (string: "confident", "balanced", or "hedged")
        """
        
        prompt = f"USER QUERY:\n{context.topic}"
        
        # We use the 70B model for reasoning
        plan_dict = await generate_json(prompt, system_prompt, model="llama-3.3-70b-versatile")
        
        # If adversarial, override to skip further work
        if plan_dict.get("classification") == "ADVERSARIAL":
            plan_dict["num_sources"] = 0
            plan_dict["run_critique"] = False
            plan_dict["search_queries"] = []

        plan = ExecutionPlan(**plan_dict)
        context.plan = plan
        
        context.events.append(PipelineEvent(
            event_type="PLAN_READY",
            agent="orchestrator",
            data=plan_dict,
            timestamp=datetime.utcnow()
        ))
        
        return context
