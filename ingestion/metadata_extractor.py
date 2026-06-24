import json
import openai
from pathlib import Path
from config.settings import get_settings

settings = get_settings()

METADATA_PROMPT = """Extract the following metadata from the first few pages of this consulting document. Return ONLY JSON.
- engagement_id: a code like ME-XX-YYYY-#### (if present, else infer from year+practice)
- client: name of the client organisation
- country: one or more GCC countries (UAE, KSA, Bahrain, Oman, Qatar, Kuwait, Jordan)
- practice: one of [Risk & Compliance, Strategy & Operations, Digital Transformation, Governance, Cybersecurity, ERM, etc.]
- year: 4-digit year

Document content (first 3000 chars):
{content}
"""

_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)


async def extract_metadata_from_document(content: str, file_path: Path) -> dict:
    """Call GPT-4o-mini to infer metadata from the document's first pages."""
    try:
        response = await _client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": METADATA_PROMPT.format(content=content[:3000])}],
        )
        meta = json.loads(response.choices[0].message.content)
        if not meta.get("engagement_id"):
            meta["engagement_id"] = f"ME-AUTO-{meta.get('year', '2024')}-001"
        if not meta.get("year"):
            meta["year"] = 2024
        return meta
    except Exception as e:
        print(f"Metadata extraction failed: {e}")
        return {
            "engagement_id": "UNKNOWN",
            "client": "Unknown",
            "country": "GCC",
            "practice": "General",
            "year": 2024,
        }
