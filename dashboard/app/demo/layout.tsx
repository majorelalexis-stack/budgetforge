"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, FolderKanban, Zap, ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/demo",          label: "Overview",  icon: LayoutDashboard },
  { href: "/demo/projects", label: "Projects",  icon: FolderKanban },
  { href: "/demo/activity", label: "Activity",  icon: Zap },
];

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--background)", color: "var(--foreground)" }}>
      {/* Demo banner */}
      <div className="w-full py-2 px-4 text-center text-sm font-semibold flex items-center justify-center gap-3 shrink-0" style={{ background: "var(--amber)", color: "#070a0f" }}>
        <span>Demo — read only</span>
        <span style={{ opacity: 0.5 }}>·</span>
        <a href="https://github.com/majorelalexis-stack/budgetforge" target="_blank" rel="noopener noreferrer" className="underline hover:opacity-80">
          Self-host for free →
        </a>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Sidebar */}
        <aside className="w-[220px] shrink-0 flex flex-col border-r" style={{ borderColor: "var(--border)", background: "var(--card)" }}>
          {/* Logo */}
          <div className="flex items-center gap-3 px-5 h-14 border-b" style={{ borderColor: "var(--border)" }}>
            <Image src="/logo.png" alt="BudgetForge" width={28} height={28} className="rounded-md" />
            <span className="font-bold text-[15px] tracking-tight">
              Budget<span style={{ color: "var(--amber)" }}>Forge</span>
            </span>
            <span className="text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded-full" style={{ background: "rgba(245,158,11,0.15)", color: "var(--amber)", border: "1px solid rgba(245,158,11,0.3)" }}>
              Demo
            </span>
          </div>

          {/* Nav */}
          <nav className="flex flex-col gap-1 p-3 flex-1">
            <p className="text-[10px] font-semibold uppercase tracking-widest px-2 mb-1 mt-2" style={{ color: "var(--muted-fg)" }}>Menu</p>
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = path === href;
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                    active
                      ? "text-[#070a0f]"
                      : "hover:bg-white/5"
                  )}
                  style={active ? { background: "var(--amber)", color: "#070a0f" } : { color: "var(--muted-fg)" }}
                >
                  <Icon className="w-4 h-4 shrink-0" strokeWidth={1.8} />
                  {label}
                </Link>
              );
            })}
          </nav>

          {/* Back link */}
          <div className="p-4 border-t" style={{ borderColor: "var(--border)" }}>
            <Link href="/" className="flex items-center gap-2 text-xs hover:opacity-80 transition-opacity" style={{ color: "var(--muted-fg)" }}>
              <ArrowLeft className="w-3.5 h-3.5" />
              Back to landing
            </Link>
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
