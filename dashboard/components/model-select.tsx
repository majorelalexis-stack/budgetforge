"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const PROVIDER_COLORS: Record<string, string> = {
  openai: "#10a37f",
  anthropic: "#d4622a",
  google: "#4285f4",
  deepseek: "#5c67f2",
  mistral: "#f54e42",
  ollama: "#22c55e",
  openrouter: "#9333ea",
  together: "#3b82f6",
  "azure-openai": "#0078d4",
  "aws-bedrock": "#ff9900",
};

interface ModelSelectProps {
  value: string;
  onChange: (value: string) => void;
  modelsByProvider: Record<string, string[]>;
  className?: string;
}

function ModelItem({
  model,
  provider,
  selected,
  onSelect,
}: {
  model: string;
  provider: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  const bg = selected
    ? "rgba(245,158,11,0.1)"
    : hovered
      ? "var(--muted)"
      : "transparent";

  return (
    <button
      type="button"
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 12px",
        fontSize: 12,
        fontFamily: "var(--font-jetbrains, monospace)",
        color: selected ? "var(--amber)" : "var(--foreground)",
        backgroundColor: bg,
        cursor: "pointer",
        textAlign: "left",
        border: "none",
        transition: "background-color 0.1s ease",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          flexShrink: 0,
          backgroundColor: PROVIDER_COLORS[provider] ?? "#64748b",
        }}
      />
      {model}
    </button>
  );
}

export function ModelSelect({
  value,
  onChange,
  modelsByProvider,
  className,
}: ModelSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentProvider =
    Object.entries(modelsByProvider).find(([, models]) =>
      models.includes(value),
    )?.[0] ?? null;

  const providerColor = currentProvider
    ? (PROVIDER_COLORS[currentProvider] ?? "#64748b")
    : "#64748b";

  const filteredProviders: Record<string, string[]> = {};
  const q = query.trim().toLowerCase();
  for (const [provider, models] of Object.entries(modelsByProvider)) {
    const filtered = q
      ? models.filter((m) => m.toLowerCase().includes(q))
      : models;
    if (filtered.length > 0) filteredProviders[provider] = filtered;
  }

  const hasResults = Object.keys(filteredProviders).length > 0;

  function openDropdown() {
    setOpen(true);
    setQuery("");
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  function selectModel(model: string) {
    onChange(model);
    setOpen(false);
    setQuery("");
  }

  function commitTyped() {
    const trimmed = query.trim();
    if (trimmed) {
      onChange(trimmed);
    }
    setOpen(false);
    setQuery("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      // If query matches exactly one result, pick it; otherwise commit raw typed value
      const allFiltered = Object.values(filteredProviders).flat();
      if (allFiltered.length === 1) {
        selectModel(allFiltered[0]);
      } else {
        commitTyped();
      }
    }
    if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }

  useEffect(() => {
    function onOutsideClick(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        commitTyped();
      }
    }
    if (open) document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [open, query]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      {/* Trigger */}
      <div
        onClick={openDropdown}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 8,
          backgroundColor: "var(--muted)",
          border: `1px solid ${open ? "rgba(245,158,11,0.5)" : "var(--border)"}`,
          borderRadius: 6,
          padding: "6px 8px",
          cursor: "text",
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            flexShrink: 0,
            backgroundColor: providerColor,
          }}
        />

        {open ? (
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              currentProvider
                ? `${currentProvider} / ${value}`
                : value || "Type or select a model"
            }
            style={{
              flex: 1,
              background: "transparent",
              border: "none",
              outline: "none",
              fontSize: 12,
              fontFamily: "var(--font-jetbrains, monospace)",
              color: "var(--foreground)",
              minWidth: 0,
            }}
          />
        ) : (
          <span
            style={{
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontSize: 12,
              fontFamily: "var(--font-jetbrains, monospace)",
              color: "var(--foreground)",
            }}
          >
            {currentProvider
              ? `${currentProvider} / ${value}`
              : value || "Type or select a model"}
          </span>
        )}

        <ChevronDown
          style={{
            width: 12,
            height: 12,
            flexShrink: 0,
            color: "var(--muted-fg)",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.15s ease",
          }}
        />
      </div>

      {/* Dropdown */}
      {open && (
        <div
          style={{
            position: "absolute",
            zIndex: 50,
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            borderRadius: 6,
            border: "1px solid var(--border)",
            backgroundColor: "var(--card)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            overflow: "hidden",
          }}
        >
          <div style={{ maxHeight: 224, overflowY: "auto" }}>
            {hasResults ? (
              Object.entries(filteredProviders).map(([provider, models]) => (
                <div key={provider}>
                  <p
                    style={{
                      position: "sticky",
                      top: 0,
                      padding: "4px 8px",
                      fontSize: 9,
                      textTransform: "uppercase",
                      letterSpacing: "0.1em",
                      color: "var(--muted-fg)",
                      fontWeight: 600,
                      backgroundColor: "var(--muted)",
                      margin: 0,
                    }}
                  >
                    {provider}
                  </p>
                  {models.map((model) => (
                    <ModelItem
                      key={model}
                      model={model}
                      provider={provider}
                      selected={value === model}
                      onSelect={() => selectModel(model)}
                    />
                  ))}
                </div>
              ))
            ) : (
              <div
                style={{
                  padding: "10px 12px",
                  fontSize: 12,
                  fontFamily: "var(--font-jetbrains, monospace)",
                  color: "var(--muted-fg)",
                }}
              >
                Press Enter to use &ldquo;{query}&rdquo;
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
