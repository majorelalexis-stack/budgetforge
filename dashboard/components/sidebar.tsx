"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { LayoutDashboard, FolderKanban, Zap, Settings, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";

const NAV = [
  { href: "/dashboard", label: "Overview",  icon: LayoutDashboard },
  { href: "/projects",  label: "Projects",  icon: FolderKanban },
  { href: "/clients",   label: "Clients",   icon: Users },
  { href: "/activity",  label: "Activity",  icon: Zap },
  { href: "/settings",  label: "Settings",  icon: Settings },
];

export function Sidebar() {
  const path = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        await api.health();
        if (!cancelled) setOnline(true);
      } catch {
        if (!cancelled) setOnline(false);
      }
    }
    check();
    const id = setInterval(check, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <>
      {/* Mobile hamburger — only shows on small screens */}
      <button
        className="fixed top-4 left-4 z-50 sm:hidden p-2 rounded-lg"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        onClick={() => setOpen((v) => !v)}
        aria-label="Toggle menu"
      >
        {open ? (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
          </svg>
        )}
      </button>

      {/* Overlay — only on mobile when open */}
      {open && (
        <div
          className="fixed inset-0 z-40 sm:hidden bg-black/40"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={cn(
          "fixed sm:static inset-y-0 left-0 z-40 transition-transform duration-200 sm:translate-x-0",
          "flex flex-col w-[220px] min-h-screen border-r border-[--border] bg-[--card]/60 backdrop-blur-sm shrink-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 h-14 border-b border-[--border]">
          <Image
            src="/logo.png"
            alt="BudgetForge"
            width={28}
            height={28}
            className="rounded-md"
            style={{ boxShadow: "0 0 12px rgba(245,158,11,0.4)" }}
          />
          <span className="font-heading font-700 text-[15px] text-[--foreground] tracking-tight">
            LLM Budget<span className="text-[--amber]">Forge</span>
          </span>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-1 p-3 flex-1">
          <p className="text-[10px] font-600 uppercase tracking-widest text-[--muted-fg] px-2 mb-1 mt-2">
            Menu
          </p>
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = path === href || path.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={cn("nav-item", active && "active")}
                onClick={() => setOpen(false)}
              >
                <Icon className="w-4 h-4 shrink-0" strokeWidth={1.8} />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Footer — theme + API status */}
        <div className="p-4 border-t border-[--border]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] text-[--muted-fg] uppercase tracking-widest font-600">Theme</span>
            <ThemeToggle />
          </div>
          {online === null ? (
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-white/5">
              <span className="w-1.5 h-1.5 rounded-full bg-[--muted-fg] animate-pulse" />
              <span className="text-[11px] text-[--muted-fg] font-mono">Checking…</span>
            </div>
          ) : online ? (
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-[--green-dim]">
              <span className="w-1.5 h-1.5 rounded-full bg-[--green] animate-pulse" />
              <span className="text-[11px] text-[--green] font-mono">API online</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-[--red-dim]">
              <span className="w-1.5 h-1.5 rounded-full bg-[--red]" />
              <span className="text-[11px] text-[--red] font-mono">API offline</span>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
