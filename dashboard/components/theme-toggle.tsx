"use client";

import { Sun, Moon } from "lucide-react";
import { useTheme } from "@/hooks/use-theme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="p-1.5 rounded-md text-[--muted-fg] hover:text-[--foreground] hover:bg-white/5 transition-all"
    >
      {theme === "dark"
        ? <Sun className="w-3.5 h-3.5" strokeWidth={1.8} />
        : <Moon className="w-3.5 h-3.5" strokeWidth={1.8} />
      }
    </button>
  );
}
