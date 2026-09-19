from app.config import OPENAI_API_KEY


class OpenAIClient:

    def __init__(self, model: str = "gpt-4o-mini"):
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. Run: pip install openai"
            ) from exc

        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
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