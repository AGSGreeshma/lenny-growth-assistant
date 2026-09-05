import httpx
import json


class OllamaClient:

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ):
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                }
            ] + messages,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

            return data["message"]["content"]