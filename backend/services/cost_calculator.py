from dataclasses import dataclass


class UnknownModelError(Exception):
    pass


@dataclass(frozen=True)
class ModelPrice:
    input_per_1m_usd: float
    output_per_1m_usd: float


_PRICES: dict[str, ModelPrice] = {
    # ── OpenAI ──────────────────────────────────────────
    "gpt-4o":               ModelPrice(5.0,    15.0),
    "gpt-4o-mini":          ModelPrice(0.15,   0.60),
    "gpt-4":                ModelPrice(30.0,   60.0),
    "gpt-4-turbo":          ModelPrice(10.0,   30.0),
    "gpt-3.5-turbo":        ModelPrice(0.50,   1.50),
    "o1":                   ModelPrice(15.0,   60.0),
    "o1-mini":              ModelPrice(3.0,    12.0),
    "o3-mini":              ModelPrice(1.10,   4.40),
    # ── Anthropic ───────────────────────────────────────
    "claude-opus-4-7":      ModelPrice(15.0,   75.0),
    "claude-sonnet-4-6":    ModelPrice(3.0,    15.0),
    "claude-haiku-4-5":     ModelPrice(0.25,   1.25),
    "claude-haiku-4-5-20251001": ModelPrice(0.25, 1.25),
    # ── Google Gemini ────────────────────────────────────
    "gemini-2.0-flash":                ModelPrice(0.10,  0.40),
    "gemini-2.0-flash-thinking":       ModelPrice(0.0,   3.50),
    "gemini-1.5-pro":                  ModelPrice(1.25,  5.00),
    "gemini-1.5-flash":                ModelPrice(0.075, 0.30),
    "gemini-1.5-flash-8b":             ModelPrice(0.0375, 0.15),
    # ── DeepSeek ────────────────────────────────────────
    "deepseek-chat":        ModelPrice(0.14,   0.28),
    "deepseek-reasoner":    ModelPrice(0.55,   2.19),
}

LOCAL_PROVIDERS = {"ollama"}


class CostCalculator:
    @staticmethod
    def get_price(model: str) -> ModelPrice:
        normalized = model.lower()
        if normalized.startswith("ollama/"):
            return ModelPrice(0.0, 0.0)
        price = _PRICES.get(normalized)
        if price is None:
            raise UnknownModelError(f"Unknown model: {model!r}")
        return price

    @staticmethod
    def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
        price = CostCalculator.get_price(model)
        return (tokens_in * price.input_per_1m_usd + tokens_out * price.output_per_1m_usd) / 1_000_000

    @staticmethod
    def is_local(provider: str) -> bool:
        return provider.lower() in LOCAL_PROVIDERS
