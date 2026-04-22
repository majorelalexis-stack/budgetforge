export type SetupTab = {
  id: string;
  label: string;
  emoji: string;
  steps: string[];
  keyLabel: string;
  urlLabel?: string;
  url?: string;
};

export function getQuickSetupTabs(apiKey: string, proxyBase: string): SetupTab[] {
  return [
    {
      id: "cursor",
      label: "Cursor",
      emoji: "⌨️",
      keyLabel: apiKey,
      url: `${proxyBase}/proxy/openai`,
      urlLabel: `${proxyBase}/proxy/openai`,
      steps: [
        "Open Cursor → Settings → Models",
        `Set API Key to: ${apiKey}`,
        `Set Base URL to: ${proxyBase}/proxy/openai`,
        "Add custom header — X-Provider-Key: your-openai-key",
        "Done — Cursor routes through BudgetForge, your key stays yours",
      ],
    },
    {
      id: "n8n",
      label: "n8n / Make",
      emoji: "⚙️",
      keyLabel: apiKey,
      url: `${proxyBase}/proxy/openai`,
      urlLabel: `${proxyBase}/proxy/openai`,
      steps: [
        "Open your AI node → Credentials",
        `Set API Key to: ${apiKey}`,
        `Set Base URL to: ${proxyBase}/proxy/openai`,
        "Add header X-Provider-Key with your real OpenAI key",
        "Done — all AI calls are tracked and limited",
      ],
    },
    {
      id: "sdk",
      label: "Python / JS SDK",
      emoji: "💻",
      keyLabel: apiKey,
      url: `${proxyBase}/proxy/openai/v1`,
      urlLabel: `${proxyBase}/proxy/openai/v1`,
      steps: [
        `Set api_key to: ${apiKey}`,
        `Set base_url to: ${proxyBase}/proxy/openai/v1`,
        "Add default_headers: { 'X-Provider-Key': 'your-openai-key' }",
        "Your original key is never stored — passed through on each request",
      ],
    },
    {
      id: "any",
      label: "Any tool",
      emoji: "🔌",
      keyLabel: apiKey,
      steps: [
        `Replace your API key with: ${apiKey}`,
        "Set Base URL to the matching proxy URL below",
        "Add header X-Provider-Key with your original provider key",
        "BudgetForge tracks usage, enforces limits — your key stays with you",
      ],
    },
  ];
}

export const PROXY_URLS: Record<string, string> = {
  openai:    "/proxy/openai/v1",
  anthropic: "/proxy/anthropic/v1",
  google:    "/proxy/google/v1",
  deepseek:  "/proxy/deepseek/v1",
  ollama:    "/proxy/ollama/v1/chat/completions",
};
