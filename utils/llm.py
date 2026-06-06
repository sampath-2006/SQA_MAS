import os
import json
import re
from dotenv import load_dotenv
from groq import AsyncGroq
from tenacity import retry, wait_exponential, stop_after_attempt

load_dotenv()

# Initialize async client
groq_client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))

def extract_json_from_text(text: str) -> dict:
    """Extracts JSON block from markdown text if present."""
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = text
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {}

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def query_llm_json(prompt: str, json_schema: dict, system_prompt: str = "") -> dict:
    """
    Queries Groq (llama3-70b-8192) asynchronously and returns a JSON dict.
    Automatically retries up to 3 times with exponential backoff on failure.
    """
    if not system_prompt:
        system_prompt = "You are a senior Software Quality Assurance engineer. Always output valid JSON that strictly matches the requested schema. Do not output anything outside the JSON block."
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt + "\n\nOutput ONLY a JSON object that strictly adheres to this schema:\n" + json.dumps(json_schema)}
    ]
    
    response = await groq_client.chat.completions.create(
        messages=messages,
        model="llama-3.3-70b-versatile",
        temperature=0.1
    )
    
    text_content = response.choices[0].message.content
    return extract_json_from_text(text_content)
