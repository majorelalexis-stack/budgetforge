import { getQuickSetupTabs, PROXY_URLS } from "../quick-setup-tabs";

const API_KEY = "bf-test-abc123";
const BASE = "https://llmbudget.maxiaworld.app";

describe("getQuickSetupTabs", () => {
  const tabs = getQuickSetupTabs(API_KEY, BASE);

  it("returns exactly 4 tabs", () => {
    expect(tabs).toHaveLength(4);
  });

  it("has tabs for cursor, n8n, any, sdk", () => {
    const ids = tabs.map((t) => t.id);
    expect(ids).toContain("cursor");
    expect(ids).toContain("n8n");
    expect(ids).toContain("any");
    expect(ids).toContain("sdk");
  });

  it("every tab has label, emoji, and at least one step", () => {
    tabs.forEach((tab) => {
      expect(tab.label).toBeTruthy();
      expect(tab.emoji).toBeTruthy();
      expect(tab.steps.length).toBeGreaterThan(0);
    });
  });

  it("every tab includes the api key", () => {
    tabs.forEach((tab) => {
      expect(tab.keyLabel).toBe(API_KEY);
    });
  });

  it("every tab step that mentions a key contains the actual key", () => {
    tabs.forEach((tab) => {
      const stepWithKey = tab.steps.find((s) => s.includes("bf-") || s.includes("API Key"));
      expect(stepWithKey).toBeTruthy();
    });
  });

  it("tabs with a url contain the proxy base url", () => {
    const tabsWithUrl = tabs.filter((t) => t.url);
    tabsWithUrl.forEach((tab) => {
      expect(tab.url).toContain(BASE);
    });
  });

  it("cursor tab url points to openai proxy", () => {
    const cursor = tabs.find((t) => t.id === "cursor")!;
    expect(cursor.url).toBe(`${BASE}/proxy/openai`);
  });

  it("sdk tab url points to openai proxy", () => {
    const sdk = tabs.find((t) => t.id === "sdk")!;
    expect(sdk.url).toBe(`${BASE}/proxy/openai`);
  });

  it("any tab has no url (generic)", () => {
    const any = tabs.find((t) => t.id === "any")!;
    expect(any.url).toBeUndefined();
  });
});

describe("PROXY_URLS", () => {
  it("has entries for all 4 providers", () => {
    expect(PROXY_URLS.openai).toBeTruthy();
    expect(PROXY_URLS.anthropic).toBeTruthy();
    expect(PROXY_URLS.google).toBeTruthy();
    expect(PROXY_URLS.deepseek).toBeTruthy();
  });
});
