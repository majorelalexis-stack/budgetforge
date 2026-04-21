"""TDD RED — CostCalculator: calcul coût tokens LLM."""
import pytest
from services.cost_calculator import CostCalculator, ModelPrice, UnknownModelError


class TestModelPriceLookup:
    def test_known_openai_model_returns_price(self):
        price = CostCalculator.get_price("gpt-4o")
        assert price.input_per_1m_usd == 5.0
        assert price.output_per_1m_usd == 15.0

    def test_known_mini_model_returns_price(self):
        price = CostCalculator.get_price("gpt-4o-mini")
        assert price.input_per_1m_usd == 0.15
        assert price.output_per_1m_usd == 0.60

    def test_known_anthropic_opus_returns_price(self):
        price = CostCalculator.get_price("claude-opus-4-7")
        assert price.input_per_1m_usd == 15.0
        assert price.output_per_1m_usd == 75.0

    def test_known_anthropic_sonnet_returns_price(self):
        price = CostCalculator.get_price("claude-sonnet-4-6")
        assert price.input_per_1m_usd == 3.0
        assert price.output_per_1m_usd == 15.0

    def test_known_anthropic_haiku_returns_price(self):
        price = CostCalculator.get_price("claude-haiku-4-5")
        assert price.input_per_1m_usd == 0.25
        assert price.output_per_1m_usd == 1.25

    def test_unknown_model_raises(self):
        with pytest.raises(UnknownModelError):
            CostCalculator.get_price("gpt-999-ultra")

    def test_ollama_model_returns_zero_price(self):
        price = CostCalculator.get_price("ollama/llama3")
        assert price.input_per_1m_usd == 0.0
        assert price.output_per_1m_usd == 0.0

    def test_model_name_case_insensitive(self):
        price = CostCalculator.get_price("GPT-4O")
        assert price.input_per_1m_usd == 5.0

    # ── Google Gemini ──────────────────────────────
    def test_gemini_flash_returns_price(self):
        price = CostCalculator.get_price("gemini-2.0-flash")
        assert price.input_per_1m_usd == 0.10
        assert price.output_per_1m_usd == 0.40

    def test_gemini_1_5_pro_returns_price(self):
        price = CostCalculator.get_price("gemini-1.5-pro")
        assert price.input_per_1m_usd == 1.25
        assert price.output_per_1m_usd == 5.00

    def test_gemini_1_5_flash_returns_price(self):
        price = CostCalculator.get_price("gemini-1.5-flash")
        assert price.input_per_1m_usd == 0.075
        assert price.output_per_1m_usd == 0.30

    # ── DeepSeek ──────────────────────────────────
    def test_deepseek_chat_returns_price(self):
        price = CostCalculator.get_price("deepseek-chat")
        assert price.input_per_1m_usd == 0.14
        assert price.output_per_1m_usd == 0.28

    def test_deepseek_reasoner_returns_price(self):
        price = CostCalculator.get_price("deepseek-reasoner")
        assert price.input_per_1m_usd == 0.55
        assert price.output_per_1m_usd == 2.19


class TestCostComputation:
    def test_zero_tokens_returns_zero_cost(self):
        cost = CostCalculator.compute_cost("gpt-4o", tokens_in=0, tokens_out=0)
        assert cost == 0.0

    def test_only_input_tokens(self):
        # 1M input tokens de gpt-4o = $5
        cost = CostCalculator.compute_cost("gpt-4o", tokens_in=1_000_000, tokens_out=0)
        assert cost == pytest.approx(5.0)

    def test_only_output_tokens(self):
        # 1M output tokens de gpt-4o = $15
        cost = CostCalculator.compute_cost("gpt-4o", tokens_in=0, tokens_out=1_000_000)
        assert cost == pytest.approx(15.0)

    def test_mixed_tokens_correct_sum(self):
        # 500k input + 200k output gpt-4o = $2.50 + $3.00 = $5.50
        cost = CostCalculator.compute_cost("gpt-4o", tokens_in=500_000, tokens_out=200_000)
        assert cost == pytest.approx(5.50)

    def test_small_request_precision(self):
        # 1000 input + 500 output claude-haiku = $0.00025 + $0.000625 = $0.000875
        cost = CostCalculator.compute_cost("claude-haiku-4-5", tokens_in=1000, tokens_out=500)
        assert cost == pytest.approx(0.000875, rel=1e-3)

    def test_ollama_model_always_zero_cost(self):
        cost = CostCalculator.compute_cost("ollama/llama3", tokens_in=100_000, tokens_out=50_000)
        assert cost == 0.0

    def test_unknown_model_raises_on_compute(self):
        with pytest.raises(UnknownModelError):
            CostCalculator.compute_cost("fake-model-xyz", tokens_in=100, tokens_out=100)

    def test_large_usage_no_overflow(self):
        # 100M tokens — doit pas overflow float
        cost = CostCalculator.compute_cost("gpt-4o", tokens_in=100_000_000, tokens_out=100_000_000)
        assert cost == pytest.approx(100 * 5.0 + 100 * 15.0)  # $500 + $1500 = $2000
