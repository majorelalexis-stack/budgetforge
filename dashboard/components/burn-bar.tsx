"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface BurnBarProps {
  pct: number;
  label?: string;
  showValue?: boolean;
  height?: number;
}

function barColor(pct: number) {
  if (pct >= 100) return "bg-red-500";
  if (pct >= 80)  return "bg-amber-500";
  return "bg-green-500";
}

function glowColor(pct: number) {
  if (pct >= 100) return "shadow-[0_0_10px_rgba(239,68,68,0.5)]";
  if (pct >= 80)  return "shadow-[0_0_10px_rgba(245,158,11,0.5)]";
  return "shadow-[0_0_10px_rgba(34,197,94,0.4)]";
}

export function BurnBar({ pct, label, showValue = true, height = 5 }: BurnBarProps) {
  const capped = Math.min(pct, 100);
  const isCritical = pct >= 100;

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {(label || showValue) && (
        <div className="flex items-center justify-between">
          {label && <span className="text-xs text-[--muted-fg]">{label}</span>}
          {showValue && (
            <span
              className={cn(
                "font-mono text-xs font-500",
                pct >= 100 ? "text-red-400" : pct >= 80 ? "text-amber-400" : "text-green-400"
              )}
            >
              {Math.round(pct)}%
            </span>
          )}
        </div>
      )}
      <div
        className="w-full rounded-full overflow-hidden bg-white/5"
        style={{ height }}
      >
        <motion.div
          className={cn(
            "h-full rounded-full",
            barColor(pct),
            isCritical && "burn-bar-critical",
            glowColor(pct)
          )}
          initial={{ width: 0 }}
          animate={{ width: `${capped}%` }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
    </div>
  );
}
