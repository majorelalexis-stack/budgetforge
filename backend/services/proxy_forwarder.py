import httpx
from core.config import settings


class ProxyForwarder:
    @staticmethod
    async def forward_openai(request_body: dict, api_key: str, timeout_s: float = 60.0) -> dict:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=request_body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_anthropic(request_body: dict, api_key: str, timeout_s: float = 60.0) -> dict:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=request_body,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_google(request_body: dict, api_key: str, timeout_s: float = 60.0) -> dict:
        """Google Gemini via their OpenAI-compatible endpoint."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                json=request_body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_deepseek(request_body: dict, api_key: str, timeout_s: float = 60.0) -> dict:
        """DeepSeek via their OpenAI-compatible endpoint."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=request_body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_openai_stream(request_body: dict, api_key: str, timeout_s: float = 120.0):
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                json=request_body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_anthropic_stream(request_body: dict, api_key: str, timeout_s: float = 120.0):
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                json=request_body,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_ollama(request_body: dict) -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={**request_body, "stream": False},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
