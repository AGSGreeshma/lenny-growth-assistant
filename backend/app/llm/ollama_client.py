import httpx


class OllamaClient:

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        timeout_seconds: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt}
            ] + messages,
            "stream": False,
            "keep_alive": "30m",
        }

        timeout = httpx.Timeout(self.timeout_seconds, connect=5.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]