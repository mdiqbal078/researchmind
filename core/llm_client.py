import os
import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

from groq import AsyncGroq
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from groq import RateLimitError, APIConnectionError, InternalServerError

# Ensure the Groq API key is present
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    # We will let it pass for now but warn, so the app doesn't crash on import
    print("WARNING: GROQ_API_KEY not found in environment.")

client = AsyncGroq(api_key=api_key or "DUMMY_KEY")

# Concurrency Semaphore to prevent burst limits on the free tier (30 RPM = 1 req / 2 sec)
# 1 concurrent request maximum to strictly queue them up.
groq_semaphore = asyncio.Semaphore(1)

@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    stop=stop_after_attempt(5)
)
async def generate_completion(prompt: str, system_prompt: str = "", model: str = "openai/gpt-oss-120b", response_format: str = "text") -> str:
    """
    Centralized LLM call with Semaphore and Exponential Backoff Retries.
    """
    async with groq_semaphore:
        # Strict sleep to enforce 30 RPM limit
        await asyncio.sleep(2.1)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.2
        }
        
        if response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}

        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    stop=stop_after_attempt(4)
)
async def generate_completion_stream(prompt: str, system_prompt: str = "", model: str = "openai/gpt-oss-120b"):
    """
    Centralized LLM call with Semaphore and Exponential Backoff Retries, yielding streamed text.
    """
    async with groq_semaphore:
        await asyncio.sleep(2.1)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True
        }
        
        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

async def generate_json(prompt: str, system_prompt: str, model: str = "openai/gpt-oss-120b") -> dict:
    """
    Helper to reliably generate and parse JSON from the LLM.
    """
    system_prompt += "\n\nYou must return ONLY valid JSON. Do not include markdown blocks like ```json."
    
    try:
        result_text = await generate_completion(prompt, system_prompt, model, response_format="json_object")
        return json.loads(result_text)
    except json.JSONDecodeError:
        # Fallback retry if the model ignored the json_object instruction (rare but happens)
        fallback_prompt = prompt + "\n\nCRITICAL: YOUR PREVIOUS OUTPUT WAS NOT VALID JSON. YOU MUST RETURN ONLY PARSABLE JSON."
        result_text = await generate_completion(fallback_prompt, system_prompt, model, response_format="json_object")
        return json.loads(result_text)
