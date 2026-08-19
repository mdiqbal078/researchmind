from agents.base import BaseAgent
from core.models import SharedContext, Source, RawChunk, PipelineEvent
from datetime import datetime
import uuid
import os

from dotenv import load_dotenv
load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Max words per source to keep total under Groq's 6000 TPM limit for extraction
# 5 sources × 400 words = 2000 words ≈ 2600 tokens + system prompt ≈ 4000 total
MAX_WORDS_PER_SOURCE = 400


class RetrievalAgent(BaseAgent):
    async def execute(self, context: SharedContext) -> SharedContext:
        if not context.plan or context.plan.num_sources == 0:
            self.logger.info("Retrieval skipped (Adversarial or 0 sources requested).")
            return context

        if not TAVILY_API_KEY:
            context.errors.append("TAVILY_API_KEY not set in .env")
            self.logger.error("TAVILY_API_KEY not found. Cannot search.")
            return context

        # ── Search with Tavily (advanced = returns full page content) ──
        search_queries = context.plan.search_queries
        self.logger.info(f"Searching Tavily for: {search_queries}")

        all_results = []
        seen_urls = set(context.urls)

        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=TAVILY_API_KEY)

            for query in search_queries:
                try:
                    response = tavily.search(
                        query=query,
                        search_depth="advanced",    # Get RICH content
                        max_results=2,
                        include_raw_content=True,   # Full page text
                    )

                    for result in response.get("results", []):
                        url = result.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(result)

                except Exception as e:
                    self.logger.warning(f"Tavily search failed for '{query}': {e}")
                    continue

        except Exception as e:
            context.errors.append(f"Tavily initialization failed: {e}")
            self.logger.error(f"Tavily error: {e}")
            return context

        # Limit to plan's num_sources
        all_results = all_results[:context.plan.num_sources]

        if not all_results:
            context.errors.append("Retrieval failed: No results from Tavily.")
            self.logger.warning("No Tavily results found.")
            return context

        self.logger.info(f"Tavily returned {len(all_results)} results with content.")

        # ── Convert to Sources + Chunks with smart truncation ──
        for result in all_results:
            url = result.get("url", "unknown")
            title = result.get("title", "Unknown Title")

            # Prefer raw_content (full page), fallback to content (snippet)
            text = result.get("raw_content") or result.get("content", "")

            if not text or len(text.strip()) < 50:
                self.logger.warning(f"Skipping {url}: content too short.")
                continue

            # Truncate to MAX_WORDS_PER_SOURCE to fit Groq's token limits
            words = text.split()
            if len(words) > MAX_WORDS_PER_SOURCE:
                text = " ".join(words[:MAX_WORDS_PER_SOURCE]) + "..."
                self.logger.info(f"Truncated {url} from {len(words)} to {MAX_WORDS_PER_SOURCE} words.")

            source = Source(
                source_id=str(uuid.uuid4()),
                url=url,
                title=title,
                fetched_at=datetime.utcnow(),
                chunk_count=1
            )
            context.sources.append(source)

            # Store the full rich text as a single chunk
            context.raw_chunks.append(RawChunk(
                chunk_id=str(uuid.uuid4()),
                source_id=source.source_id,
                text=text,
                position=0
            ))

        total_words = sum(len(c.text.split()) for c in context.raw_chunks)
        self.logger.info(f"Created {len(context.sources)} sources, {len(context.raw_chunks)} chunks ({total_words} total words).")

        context.events.append(PipelineEvent(
            event_type="AGENT_DONE",
            agent="retrieval",
            data={"sources_count": len(context.sources), "chunks_count": len(context.raw_chunks)},
            timestamp=datetime.utcnow()
        ))

        return context
