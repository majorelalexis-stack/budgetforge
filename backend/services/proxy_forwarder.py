import httpx
from core.config import settings


class ProxyForwarder:
    @staticmethod
    async def forward_openai(
        request_body: dict, api_key: str, timeout_s: float = 60.0
    ) -> dict:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_anthropic(
        request_body: dict, api_key: str, timeout_s: float = 60.0
    ) -> dict:
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
    async def forward_google(
        request_body: dict, api_key: str, timeout_s: float = 60.0
    ) -> dict:
        """Google Gemini via their OpenAI-compatible endpoint."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_deepseek(
        request_body: dict, api_key: str, timeout_s: float = 60.0
    ) -> dict:
        """DeepSeek via their OpenAI-compatible endpoint."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_openai_stream(
        request_body: dict, api_key: str, timeout_s: float = 120.0
    ):
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_anthropic_stream(
        request_body: dict, api_key: str, timeout_s: float = 120.0
    ):
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
    async def forward_google_stream(
        request_body: dict, api_key: str, timeout_s: float = 120.0
    ):
        """Google Gemini OpenAI-compat streaming."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_deepseek_stream(
        request_body: dict, api_key: str, timeout_s: float = 120.0
    ):
        """DeepSeek OpenAI-compat streaming."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                "https://api.deepseek.com/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_mistral(
        request_body: dict, api_key: str, timeout_s: float = 60.0
    ) -> dict:
        """Mistral AI via their OpenAI-compatible endpoint."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.mistral.ai/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_mistral_stream(
        request_body: dict, api_key: str, timeout_s: float = 120.0
    ):
        """Mistral AI OpenAI-compat streaming."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                "https://api.mistral.ai/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_openrouter(
        request_body: dict, api_key: str, timeout_s: float = 60.0
    ) -> dict:
        """OpenRouter via their OpenAI-compatible endpoint."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://llmbudget.maxiaworld.app",  # Required by OpenRouter
                    "X-Title": "BudgetForge",  # Optional but recommended
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_openrouter_stream(
        request_body: dict, api_key: str, timeout_s: float = 120.0
    ):
        """OpenRouter streaming via OpenAI-compatible endpoint."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://budgetforge.io",
                    "X-Title": "BudgetForge",
                },
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_together(
        request_body: dict, api_key: str, timeout_s: float = 60.0
    ) -> dict:
        """Together AI via leur endpoint OpenAI-compatible."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.together.xyz/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_together_stream(
        request_body: dict, api_key: str, timeout_s: float = 120.0
    ):
        """Together AI streaming via OpenAI-compatible endpoint."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                "https://api.together.xyz/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_azure_openai(
        request_body: dict, api_key: str, base_url: str, timeout_s: float = 60.0
    ) -> dict:
        """Azure OpenAI via leur endpoint OpenAI-compatible."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{base_url}/openai/deployments/{request_body.get('model', 'gpt-4o')}/chat/completions?api-version=2024-02-15-preview",
                json=request_body,
                headers={"api-key": api_key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_azure_openai_stream(
        request_body: dict, api_key: str, base_url: str, timeout_s: float = 120.0
    ):
        """Azure OpenAI streaming via leur endpoint OpenAI-compatible."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                f"{base_url}/openai/deployments/{request_body.get('model', 'gpt-4o')}/chat/completions?api-version=2024-02-15-preview",
                json=request_body,
                headers={"api-key": api_key, "Content-Type": "application/json"},
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

    @staticmethod
    async def forward_ollama_stream(request_body: dict, timeout_s: float = 120.0):
        """Streaming natif Ollama — retourne des chunks newline-JSON."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/chat",
                json={**request_body, "stream": True},
                headers={"Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_ollama_openai_compat(
        request_body: dict, api_key: str = "", timeout_s: float = 60.0
    ) -> dict:
        """Endpoint OpenAI-compatible d'Ollama (/v1/chat/completions)."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/v1/chat/completions",
                json=request_body,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def forward_ollama_openai_compat_stream(
        request_body: dict, api_key: str = "", timeout_s: float = 120.0
    ):
        """Streaming OpenAI-compatible via Ollama — retourne des chunks SSE."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/v1/chat/completions",
                json=request_body,
                headers={"Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    @staticmethod
    async def forward_aws_bedrock(
        request_body: dict, api_key: str = "", timeout_s: float = 60.0
    ) -> dict:
        """AWS Bedrock via leur API native."""
        from services.aws_bedrock_client import aws_bedrock_client

        if not aws_bedrock_client.is_configured():
            raise ValueError("AWS Bedrock non configuré")

        # Extraire les données de la requête
        model = request_body.get("model", "anthropic.claude-v2")
        messages = request_body.get("messages", [])
        temperature = request_body.get("temperature", 0.7)
        max_tokens = request_body.get("max_tokens", 1000)

        # Convertir en format Bedrock
        bedrock_body = aws_bedrock_client.convert_to_bedrock_format(
            messages, temperature, max_tokens
        )

        # Invoquer le modèle
        bedrock_response = aws_bedrock_client.invoke_model(model, bedrock_body)

        # Convertir en format OpenAI
        openai_response = aws_bedrock_client.convert_from_bedrock_format(
            bedrock_response, model
        )

        return openai_response

    @staticmethod
    async def forward_aws_bedrock_stream(
        request_body: dict, api_key: str = "", timeout_s: float = 120.0
    ):
        """AWS Bedrock streaming (non supporté pour l'instant)."""
        # AWS Bedrock ne supporte pas le streaming natif via leur API
        # On retourne une erreur pour l'instant
        raise NotImplementedError(
            "AWS Bedrock ne supporte pas le streaming via cette API"
        )
