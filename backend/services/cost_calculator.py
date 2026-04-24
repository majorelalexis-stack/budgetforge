from dataclasses import dataclass

from .dynamic_pricing import get_dynamic_price, UnknownModelError


@dataclass(frozen=True)
class ModelPrice:
    input_per_1m_usd: float
    output_per_1m_usd: float


# Prix statiques pour compatibilité (fallback)
_PRICES: dict[str, ModelPrice] = {
    # ── OpenAI ──────────────────────────────────────────
    "gpt-4o": ModelPrice(5.0, 15.0),
    "gpt-4o-mini": ModelPrice(0.15, 0.60),
    "gpt-4": ModelPrice(30.0, 60.0),
    "gpt-4-turbo": ModelPrice(10.0, 30.0),
    "gpt-3.5-turbo": ModelPrice(0.50, 1.50),
    "o1": ModelPrice(15.0, 60.0),
    "o1-mini": ModelPrice(3.0, 12.0),
    "o3-mini": ModelPrice(1.10, 4.40),
    # ── Anthropic ───────────────────────────────────────
    "claude-opus-4-7": ModelPrice(15.0, 75.0),
    "claude-sonnet-4-6": ModelPrice(3.0, 15.0),
    "claude-haiku-4-5": ModelPrice(0.25, 1.25),
    "claude-haiku-4-5-20251001": ModelPrice(0.25, 1.25),
    # ── Google Gemini ────────────────────────────────────
    "gemini-2.0-flash": ModelPrice(0.10, 0.40),
    "gemini-2.0-flash-thinking": ModelPrice(0.0, 3.50),
    "gemini-1.5-pro": ModelPrice(1.25, 5.00),
    "gemini-1.5-flash": ModelPrice(0.075, 0.30),
    "gemini-1.5-flash-8b": ModelPrice(0.0375, 0.15),
    # ── DeepSeek ────────────────────────────────────────
    "deepseek-chat": ModelPrice(0.14, 0.28),
    "deepseek-reasoner": ModelPrice(0.55, 2.19),
    # ── Mistral AI ───────────────────────────────────────
    "mistral-large-latest": ModelPrice(2.00, 6.00),
    "mistral-small-latest": ModelPrice(0.20, 0.60),
    "mistral-nemo": ModelPrice(0.15, 0.15),
    "codestral-latest": ModelPrice(0.30, 0.90),
    "open-mistral-7b": ModelPrice(0.25, 0.25),
    "open-mixtral-8x7b": ModelPrice(0.70, 0.70),
    "open-mixtral-8x22b": ModelPrice(2.00, 6.00),
    # ── Ollama ──────────────────────────────────────────
    "ollama/llama2": ModelPrice(0.0, 0.0),
    "ollama/codellama": ModelPrice(0.0, 0.0),
    "ollama/mistral": ModelPrice(0.0, 0.0),
    "ollama/phi3": ModelPrice(0.0, 0.0),
    # ── AWS Bedrock ─────────────────────────────────────
    "anthropic.claude-v2": ModelPrice(8.00, 24.00),
    "anthropic.claude-v2:1": ModelPrice(8.00, 24.00),
    "anthropic.claude-3-haiku": ModelPrice(0.80, 4.00),
    "anthropic.claude-3-sonnet": ModelPrice(3.00, 15.00),
    "anthropic.claude-3-opus": ModelPrice(15.00, 75.00),
    "meta.llama2-13b-chat": ModelPrice(0.75, 0.75),
    "meta.llama2-70b-chat": ModelPrice(2.05, 2.05),
    "meta.llama3-8b-instruct": ModelPrice(0.60, 0.60),
    "meta.llama3-70b-instruct": ModelPrice(2.65, 2.65),
}

LOCAL_PROVIDERS = {"ollama"}


class CostCalculator:
    @staticmethod
    async def get_price(model: str) -> ModelPrice:
        """Obtient le prix d'un modèle via le système dynamique."""
        normalized = model.lower()
        if normalized.startswith("ollama/"):
            return ModelPrice(0.0, 0.0)

        try:
            # Essayer d'abord le système dynamique
            return await get_dynamic_price(model)
        except (ValueError, Exception):
            # Fallback vers les prix statiques
            price = _PRICES.get(normalized)
            if price is None:
                raise UnknownModelError(f"Unknown model: {model!r}")
            return price

    @staticmethod
    async def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
        """Calcule le coût en utilisant le système de prix dynamique."""
        price = await CostCalculator.get_price(model)
        return (
            tokens_in * price.input_per_1m_usd + tokens_out * price.output_per_1m_usd
        ) / 1_000_000

    @staticmethod
    def is_local(provider: str) -> bool:
        return provider.lower() in LOCAL_PROVIDERS
