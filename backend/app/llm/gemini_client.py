"""
Gemini client, deliberately built on the same `openai` pip package
OpenAIClient uses -- not a separate Google SDK. Gemini exposes an
OpenAI-compatible endpoint (GEMINI_BASE_URL in app/config.py); pointing the
existing AsyncOpenAI client at it, with a Gemini API key and model name, is
enough. This keeps the integration to "one more thin client class" instead
of a second SDK with its own request/response shape to maintain.
"""

from app.config import GEMINI_API_KEY, GEMINI_BASE_URL, GEMINI_MODEL


class GeminiClient:

    def __init__(self, model: str = GEMINI_MODEL):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. Run: pip install openai"
            ) from exc

        self.client = AsyncOpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL)
        self.model = model

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ):
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                }
            ] + messages,
        )

        return response.choices[0].message.content
