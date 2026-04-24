"use client";

import { motion } from "framer-motion";
import {
  Key,
  Bell,
  Zap,
  Copy,
  Check,
  Info,
  Save,
  Eye,
  EyeOff,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { Toast } from "@/components/toast";
import { api, type SiteSettings } from "@/lib/api";

const PROVIDERS = [
  {
    name: "OpenAI",
    env: "OPENAI_API_KEY",
    models: [
      "gpt-4o",
      "gpt-4o-mini",
      "gpt-4-turbo",
      "gpt-3.5-turbo",
      "o1",
      "o1-mini",
      "o3-mini",
    ],
    color: "#10a37f",
    note: "Required for /proxy/openai",
  },
  {
    name: "Anthropic",
    env: "ANTHROPIC_API_KEY",
    models: ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
    color: "#d4622a",
    note: "Required for /proxy/anthropic",
  },
  {
    name: "Google Gemini",
    env: "GOOGLE_API_KEY",
    models: [
      "gemini-2.0-flash",
      "gemini-1.5-pro",
      "gemini-1.5-flash",
      "gemini-2.0-flash-thinking",
    ],
    color: "#4285f4",
    note: "Required for /proxy/google (OpenAI-compat endpoint)",
  },
  {
    name: "DeepSeek",
    env: "DEEPSEEK_API_KEY",
    models: ["deepseek-chat", "deepseek-reasoner"],
    color: "#5c67f2",
    note: "Required for /proxy/deepseek (OpenAI-compat endpoint)",
  },
  {
    name: "Mistral",
    env: "MISTRAL_API_KEY",
    models: ["mistral-large-latest", "mistral-small-latest", "mistral-nemo", "codestral-latest"],
    color: "#f54e42",
    note: "Required for /proxy/mistral (OpenAI-compat endpoint)",
  },
  {
    name: "Ollama",
    env: "OLLAMA_BASE_URL",
    models: ["llama3", "mistral", "qwen3", "gemma3", "… any local model"],
    color: "#22c55e",
    note: "Local — no API key needed. Default: http://localhost:11434",
  },
  {
    name: "OpenRouter",
    env: "OPENROUTER_API_KEY",
    models: [
      "openrouter/anthropic/claude-3.5-sonnet",
      "openrouter/openai/gpt-4",
      "openrouter/google/gemini-pro",
    ],
    color: "#9333ea",
    note: "Required for /proxy/openrouter (OpenAI-compat endpoint)",
  },
  {
    name: "Together AI",
    env: "TOGETHER_API_KEY",
    models: [
      "togethercomputer/LLaMA-2-7B-32K",
      "togethercomputer/LLaMA-2-70B-32K",
      "togethercomputer/LLaMA-3-8B-32K-Instruct",
    ],
    color: "#ff6b35",
    note: "Required for /proxy/together (OpenAI-compat endpoint)",
  },
  {
    name: "Azure OpenAI",
    env: "AZURE_OPENAI_API_KEY",
    models: [
      "azure/gpt-4o",
      "azure/gpt-4o-mini",
      "azure/gpt-4-turbo",
      "azure/gpt-3.5-turbo",
    ],
    color: "#0078d4",
    note: "Required for /proxy/azure-openai (OpenAI-compat endpoint)",
  },
  {
    name: "AWS Bedrock",
    env: "AWS_BEDROCK_ACCESS_KEY",
    models: [
      "anthropic.claude-v2",
      "anthropic.claude-3-haiku",
      "anthropic.claude-3-sonnet",
      "anthropic.claude-3-opus",
      "meta.llama2-13b-chat",
      "meta.llama2-70b-chat",
      "meta.llama3-8b-instruct",
      "meta.llama3-70b-instruct",
    ],
    color: "#ff9900",
    note: "Required for /proxy/aws-bedrock (AWS credentials)",
  },
];

const PROXY_ENDPOINTS = [
  {
    method: "POST",
    path: "/proxy/openai/v1/chat/completions",
    provider: "OpenAI",
    note: "Drop-in replacement",
  },
  {
    method: "POST",
    path: "/proxy/anthropic/v1/messages",
    provider: "Anthropic",
    note: "Anthropic SDK format",
  },
  {
    method: "POST",
    path: "/proxy/google/v1/chat/completions",
    provider: "Google",
    note: "OpenAI-compat",
  },
  {
    method: "POST",
    path: "/proxy/deepseek/v1/chat/completions",
    provider: "DeepSeek",
    note: "OpenAI-compat",
  },
  {
    method: "POST",
    path: "/proxy/mistral/v1/chat/completions",
    provider: "Mistral",
    note: "OpenAI-compat",
  },
  {
    method: "POST",
    path: "/proxy/openrouter/v1/chat/completions",
    provider: "OpenRouter",
    note: "OpenAI-compat",
  },
  {
    method: "POST",
    path: "/proxy/together/v1/chat/completions",
    provider: "Together AI",
    note: "OpenAI-compat",
  },
  {
    method: "POST",
    path: "/proxy/azure-openai/v1/chat/completions",
    provider: "Azure OpenAI",
    note: "OpenAI-compat",
  },
  {
    method: "POST",
    path: "/proxy/aws-bedrock/v1/chat/completions",
    provider: "AWS Bedrock",
    note: "AWS Bedrock API",
  },
  {
    method: "POST",
    path: "/proxy/ollama/api/chat",
    provider: "Ollama",
    note: "Free, tokens counted",
  },
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <button
      onClick={copy}
      className="p-1 rounded text-[--muted-fg] hover:text-[--amber] transition-colors"
      title="Copy env var name"
    >
      {copied ? (
        <Check className="w-3 h-3 text-green-400" />
      ) : (
        <Copy className="w-3 h-3" />
      )}
    </button>
  );
}

function SmtpForm({ onSaved }: { onSaved: () => void }) {
  const [form, setForm] = useState({
    smtp_host: "",
    smtp_port: "587",
    smtp_user: "",
    smtp_password: "",
    alert_from_email: "",
  });
  const [passwordSet, setPasswordSet] = useState(false);
  const [showPass, setShowPass] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.settings
      .get()
      .then((s: SiteSettings) => {
        setForm({
          smtp_host: s.smtp_host,
          smtp_port: String(s.smtp_port),
          smtp_user: s.smtp_user,
          smtp_password: "",
          alert_from_email: s.alert_from_email,
        });
        setPasswordSet(s.smtp_password_set);
      })
      .catch((e) => {
        setError(
          e instanceof Error
            ? e.message
            : "Could not load SMTP settings. Please refresh.",
        );
      });
  }, []);

  async function save() {
    setSaving(true);
    setError("");
    try {
      const body: Record<string, string | number> = {
        smtp_host: form.smtp_host,
        smtp_port: parseInt(form.smtp_port, 10) || 587,
        smtp_user: form.smtp_user,
        alert_from_email: form.alert_from_email,
      };
      if (form.smtp_password) body.smtp_password = form.smtp_password;
      const updated = await api.settings.update(body);
      setPasswordSet(updated.smtp_password_set);
      setForm((f) => ({ ...f, smtp_password: "" }));
      setSaved(true);
      onSaved();
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    background: "var(--background)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "6px 10px",
    fontSize: 12,
    fontFamily: "var(--font-jetbrains, monospace)",
    color: "var(--foreground)",
    outline: "none",
  };

  return (
    <div className="px-5 py-4 flex flex-col gap-4">
      <p className="text-xs text-[--muted-fg]">
        Configure your SMTP server to receive email alerts when a budget
        threshold is reached.
      </p>

      <div className="grid grid-cols-2 gap-3">
        {/* SMTP_HOST */}
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[10px] text-[--amber] uppercase tracking-wider">
            SMTP_HOST
          </label>
          <input
            style={inputStyle}
            placeholder="smtp.gmail.com"
            value={form.smtp_host}
            onChange={(e) =>
              setForm((f) => ({ ...f, smtp_host: e.target.value }))
            }
          />
        </div>

        {/* SMTP_PORT */}
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[10px] text-[--amber] uppercase tracking-wider">
            SMTP_PORT
          </label>
          <input
            style={inputStyle}
            placeholder="587"
            type="number"
            value={form.smtp_port}
            onChange={(e) =>
              setForm((f) => ({ ...f, smtp_port: e.target.value }))
            }
          />
        </div>

        {/* SMTP_USER */}
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[10px] text-[--amber] uppercase tracking-wider">
            SMTP_USER
          </label>
          <input
            style={inputStyle}
            placeholder="you@domain.com"
            value={form.smtp_user}
            onChange={(e) =>
              setForm((f) => ({ ...f, smtp_user: e.target.value }))
            }
          />
        </div>

        {/* SMTP_PASSWORD */}
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[10px] text-[--amber] uppercase tracking-wider">
            SMTP_PASSWORD
            {passwordSet && (
              <span className="ml-2 text-green-400 normal-case">
                ● configured
              </span>
            )}
          </label>
          <div className="relative">
            <input
              style={{ ...inputStyle, paddingRight: 32 }}
              type={showPass ? "text" : "password"}
              placeholder={
                passwordSet ? "••••••••  (leave blank to keep)" : "App password"
              }
              value={form.smtp_password}
              onChange={(e) =>
                setForm((f) => ({ ...f, smtp_password: e.target.value }))
              }
            />
            <button
              type="button"
              onClick={() => setShowPass((v) => !v)}
              style={{
                position: "absolute",
                right: 8,
                top: "50%",
                transform: "translateY(-50%)",
                color: "var(--muted-fg)",
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: 0,
              }}
            >
              {showPass ? (
                <EyeOff className="w-3 h-3" />
              ) : (
                <Eye className="w-3 h-3" />
              )}
            </button>
          </div>
        </div>

        {/* ALERT_FROM_EMAIL — full width */}
        <div className="col-span-2 flex flex-col gap-1">
          <label className="font-mono text-[10px] text-[--amber] uppercase tracking-wider">
            ALERT_FROM_EMAIL
          </label>
          <input
            style={inputStyle}
            placeholder="alerts@yourapp.io"
            value={form.alert_from_email}
            onChange={(e) =>
              setForm((f) => ({ ...f, alert_from_email: e.target.value }))
            }
          />
        </div>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="flex justify-end">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-600 transition-colors"
          style={{
            background: saved
              ? "rgba(34,197,94,0.15)"
              : "rgba(245,158,11,0.12)",
            color: saved ? "#22c55e" : "var(--amber)",
            border: `1px solid ${saved ? "rgba(34,197,94,0.3)" : "rgba(245,158,11,0.3)"}`,
            cursor: saving ? "not-allowed" : "pointer",
          }}
        >
          {saved ? <Check className="w-3 h-3" /> : <Save className="w-3 h-3" />}
          {saved ? "Saved" : saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const [toast, setToast] = useState<{ show: boolean; message: string }>({
    show: false,
    message: "",
  });

  return (
    <Shell>
      <div className="p-6 max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="font-heading font-800 text-2xl tracking-tight mb-1">
            Settings
          </h1>
          <p className="text-[--muted-fg] text-sm">
            Configure provider API keys in{" "}
            <code className="font-mono text-[--foreground] bg-white/5 px-1.5 py-0.5 rounded text-xs">
              budgetforge/backend/.env
            </code>
          </p>
        </motion.div>

        <div className="flex flex-col gap-5">
          {/* Info banner */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-3 px-4 py-3 rounded-md bg-[--amber-dim] border border-[--amber]/20"
          >
            <Info className="w-4 h-4 text-[--amber] mt-0.5 shrink-0" />
            <p className="text-xs text-[--amber]/80 leading-relaxed">
              API keys are stored on the backend only. They are never sent to
              the browser. Only the project{" "}
              <code className="font-mono bg-[--amber]/10 px-1 rounded">
                bf-xxx
              </code>{" "}
              key is used by client apps.
            </p>
          </motion.div>

          {/* Provider API keys */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="card-base overflow-hidden"
          >
            <div className="flex items-center gap-2 px-5 py-4 border-b border-[--border]">
              <Key className="w-4 h-4 text-[--amber]" />
              <h2 className="font-heading font-700 text-sm">
                Provider API Keys
              </h2>
              <span className="ml-auto text-[10px] text-[--muted-fg] bg-white/5 px-2 py-0.5 rounded-full">
                Read-only reference
              </span>
            </div>
            <div className="divide-y divide-[--border]">
              {PROVIDERS.map((p) => (
                <div key={p.name} className="px-5 py-4 flex items-start gap-4">
                  {/* Color dot */}
                  <div
                    className="w-2 h-2 rounded-full mt-1.5 shrink-0"
                    style={{
                      background: p.color,
                      boxShadow: `0 0 6px ${p.color}`,
                    }}
                  />
                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-600 text-[--foreground]">
                        {p.name}
                      </span>
                      <span className="text-[10px] text-[--muted-fg] italic">
                        {p.note}
                      </span>
                    </div>
                    {/* Env var */}
                    <div className="flex items-center gap-1.5 mb-2">
                      <code className="font-mono text-xs text-[--amber] bg-[--amber-dim] px-2 py-0.5 rounded">
                        {p.env}
                      </code>
                      <CopyButton text={p.env} />
                    </div>
                    {/* Models */}
                    <div className="flex flex-wrap gap-1">
                      {p.models.map((m) => (
                        <span
                          key={m}
                          className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-[--muted-fg]"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* SMTP */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="card-base overflow-hidden"
          >
            <div className="flex items-center gap-2 px-5 py-4 border-b border-[--border]">
              <Bell className="w-4 h-4 text-[--amber]" />
              <h2 className="font-heading font-700 text-sm">
                Alert Configuration
              </h2>
              <span className="ml-auto text-[10px] text-[--muted-fg] bg-white/5 px-2 py-0.5 rounded-full">
                Optional
              </span>
            </div>
            <SmtpForm
              onSaved={() =>
                setToast({ show: true, message: "Settings saved" })
              }
            />
          </motion.div>

          {/* Proxy endpoints */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="card-base overflow-hidden"
          >
            <div className="flex items-center gap-2 px-5 py-4 border-b border-[--border]">
              <Zap className="w-4 h-4 text-[--amber]" />
              <h2 className="font-heading font-700 text-sm">Proxy Endpoints</h2>
            </div>
            <div className="divide-y divide-[--border]">
              {PROXY_ENDPOINTS.map(({ method, path, provider, note }) => (
                <div key={path} className="flex items-center gap-3 px-5 py-3">
                  <span className="text-[10px] font-600 bg-[--amber-dim] text-[--amber] px-2 py-0.5 rounded font-mono uppercase shrink-0">
                    {method}
                  </span>
                  <code className="font-mono text-xs text-[--foreground] flex-1">
                    {path}
                  </code>
                  <CopyButton text={`http://localhost:8011${path}`} />
                  <span className="text-[10px] text-[--muted-fg] shrink-0">
                    {provider} · {note}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
      <Toast
        show={toast.show}
        message={toast.message}
        onClose={() => setToast({ show: false, message: "" })}
      />
    </Shell>
  );
}
