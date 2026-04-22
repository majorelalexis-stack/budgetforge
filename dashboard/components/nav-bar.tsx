"use client";
import { useState } from "react";
import Image from "next/image";
import Link from "next/link";

const LINKS = [
  { label: "How it works", href: "#how", external: false },
  { label: "Pricing", href: "#pricing", external: false },
  { label: "Live preview", href: "/demo", external: false },
] as const;

export function NavBar() {
  const [open, setOpen] = useState(false);

  return (
    <nav
      className="px-6 py-4 relative"
      style={{ borderBottom: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <Image src="/logo.png" alt="BudgetForge" width={36} height={36} className="rounded-lg" />
          <span className="font-bold text-lg tracking-tight">
            LLM <span style={{ color: "var(--amber)" }}>BudgetForge</span>
          </span>
        </div>

        {/* Desktop links */}
        <div className="hidden sm:flex items-center gap-6 text-sm">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} style={{ color: "#c8d8e8" }} className="hover:opacity-80">
              {l.label}
            </a>
          ))}
          <Link
            href="/portal"
            className="px-4 py-1.5 rounded-lg font-semibold text-xs transition-opacity hover:opacity-90"
            style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}
          >
            My keys →
          </Link>
        </div>

        {/* Mobile: My keys always visible + hamburger */}
        <div className="flex sm:hidden items-center gap-3">
          <Link
            href="/portal"
            className="px-3 py-1.5 rounded-lg font-semibold text-xs transition-opacity hover:opacity-90"
            style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}
          >
            My keys →
          </Link>
          <button
            onClick={() => setOpen((o) => !o)}
            aria-label="Toggle menu"
            className="p-2 rounded-md"
            style={{ color: "#c8d8e8" }}
          >
            {open ? (
              <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobile dropdown */}
      {open && (
        <div
          className="sm:hidden absolute left-0 right-0 top-full z-50 flex flex-col gap-1 px-6 py-4"
          style={{ background: "var(--background)", borderBottom: "1px solid var(--border)" }}
        >
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="py-2 text-sm hover:opacity-80"
              style={{ color: "#c8d8e8" }}
            >
              {l.label}
            </a>
          ))}
        </div>
      )}
    </nav>
  );
}
