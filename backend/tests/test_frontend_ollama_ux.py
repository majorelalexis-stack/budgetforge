"""
Frontend source-scan tests for Ollama UX.

Verifies that user-facing pages/components expose Ollama correctly:
pricing lists it, portal shows the proxy URL, quick-setup includes it,
settings registers the OpenAI-compat endpoint, and provider breakdown
shows "local" instead of "$0.0000" for free Ollama calls.
"""
import os

DASHBOARD_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "dashboard")
)


def _read(rel: str) -> str:
    path = os.path.join(DASHBOARD_ROOT, rel)
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestPricingOllama:
    """Pricing section must mention Ollama so visitors know local LLMs are free."""

    def test_free_plan_includes_ollama(self):
        src = _read("components/pricing-section.tsx")
        # The Free plan feature list must reference Ollama or local LLMs
        free_block_idx = src.index('"free"')
        pro_block_idx = src.index('"pro"')
        free_block = src[free_block_idx:pro_block_idx]
        assert "Ollama" in free_block or "local" in free_block.lower(), (
            "Free plan features must mention Ollama / local LLMs"
        )

    def test_pro_plan_providers_includes_ollama(self):
        src = _read("components/pricing-section.tsx")
        pro_block_idx = src.index('"pro"')
        agency_block_idx = src.index('"agency"')
        pro_block = src[pro_block_idx:agency_block_idx]
        assert "Ollama" in pro_block, (
            "Pro plan features must list Ollama as a supported provider"
        )


class TestPortalOllamaUrl:
    """Portal page must show the Ollama proxy URL next to the OpenAI one."""

    def test_portal_shows_ollama_proxy_path(self):
        src = _read("app/portal/page.tsx")
        assert "/proxy/ollama" in src, (
            "portal/page.tsx must include a /proxy/ollama URL"
        )

    def test_portal_ollama_section_label(self):
        src = _read("app/portal/page.tsx")
        # Should have a label like "Proxy URL (Ollama)" similar to "Proxy URL (OpenAI)"
        assert "Ollama" in src, (
            "portal/page.tsx must have an Ollama-labeled section"
        )

    def test_portal_ollama_no_provider_key_note(self):
        src = _read("app/portal/page.tsx")
        # Ollama note: no X-Provider-Key header required
        assert "no" in src.lower() and "key" in src.lower(), (
            "portal/page.tsx must note that Ollama requires no provider key"
        )


class TestQuickSetupTabsOllama:
    """PROXY_URLS must expose the Ollama OpenAI-compat endpoint."""

    def test_proxy_urls_has_ollama_key(self):
        src = _read("lib/quick-setup-tabs.ts")
        assert "ollama" in src, (
            "quick-setup-tabs.ts PROXY_URLS must have an ollama entry"
        )

    def test_proxy_urls_ollama_uses_openai_compat_path(self):
        src = _read("lib/quick-setup-tabs.ts")
        assert "/proxy/ollama/v1" in src, (
            "ollama PROXY_URL must use the OpenAI-compat path /proxy/ollama/v1"
        )

    def test_quick_integration_summary_mentions_ollama(self):
        src = _read("components/quick-integration.tsx")
        # The "All proxy URLs" summary text must mention Ollama
        assert "Ollama" in src or "ollama" in src, (
            "quick-integration.tsx must mention Ollama in its proxy URL listing"
        )


class TestSettingsProxyEndpoints:
    """Settings page PROXY_ENDPOINTS must include the Ollama OpenAI-compat endpoint."""

    def test_settings_has_ollama_openai_compat_endpoint(self):
        src = _read("app/settings/page.tsx")
        assert "/proxy/ollama/v1/chat/completions" in src, (
            "settings/page.tsx PROXY_ENDPOINTS must include /proxy/ollama/v1/chat/completions"
        )

    def test_settings_has_two_ollama_endpoints(self):
        src = _read("app/settings/page.tsx")
        # Native (/proxy/ollama/api/chat) + OpenAI-compat (/proxy/ollama/v1/chat/completions)
        assert src.count("/proxy/ollama") >= 2, (
            "settings/page.tsx must list at least 2 Ollama proxy endpoints (native + OpenAI-compat)"
        )


class TestProviderBreakdownOllamaCost:
    """ProviderBreakdownChart must show 'local' for Ollama calls, not '$0.0000'."""

    def test_provider_breakdown_has_ollama_conditional(self):
        src = _read("app/projects/[id]/page.tsx")
        has_conditional = (
            'e.name === "ollama"' in src
            or "e.name === 'ollama'" in src
            or "isOllama" in src
        )
        assert has_conditional, (
            "ProviderBreakdownChart must have a conditional for ollama cost display"
        )

    def test_provider_breakdown_ollama_shows_local_label(self):
        src = _read("app/projects/[id]/page.tsx")
        # "local" label must be present near ollama handling
        assert "local" in src, (
            "ProviderBreakdownChart must display 'local' for Ollama cost (it's $0)"
        )
