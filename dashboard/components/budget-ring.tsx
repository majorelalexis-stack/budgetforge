"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useSpring, useTransform } from "framer-motion";

interface BudgetRingProps {
  pct: number;        // 0–100
  used: number;       // in $
  budget: number;     // in $
  size?: number;
  strokeWidth?: number;
}

function statusColor(pct: number) {
  if (pct >= 100) return "#ef4444";
  if (pct >= 80)  return "#f59e0b";
  return "#22c55e";
}

function statusLabel(pct: number) {
  if (pct >= 100) return "Exceeded";
  if (pct >= 80)  return "Warning";
  return "Healthy";
}

export function BudgetRing({
  pct,
  used,
  budget,
  size = 160,
  strokeWidth = 10,
}: BudgetRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const color = statusColor(pct);

  const spring = useSpring(0, { stiffness: 60, damping: 18, mass: 0.8 });
  const offset = useTransform(spring, (v) =>
    circumference * (1 - Math.min(v, 100) / 100)
  );
  const displayPct = useTransform(spring, (v) => `${Math.min(Math.round(v), 100)}%`);

  useEffect(() => { spring.set(pct); }, [pct, spring]);

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90" style={{ overflow: "visible" }}>
          {/* Glow filter */}
          <defs>
            <filter id="ring-glow">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          {/* Track */}
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />
          {/* Progress */}
          <motion.circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            filter="url(#ring-glow)"
            style={{ transition: "stroke 0.3s ease" }}
          />
        </svg>
        {/* Center label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-0.5">
          <motion.span
            className="font-heading font-800 text-3xl"
            style={{ color }}
          >
            {displayPct}
          </motion.span>
          <span
            className="text-[10px] font-600 uppercase tracking-widest px-2 py-0.5 rounded-full"
            style={{
              background: `${color}18`,
              color,
            }}
          >
            {statusLabel(pct)}
          </span>
        </div>
      </div>
      {/* Legend */}
      <div className="flex items-baseline gap-1.5 text-center">
        <span className="font-mono text-sm font-500 text-[--foreground]">
          ${used.toFixed(4)}
        </span>
        <span className="text-[--muted-fg] text-xs">of</span>
        <span className="font-mono text-sm font-500 text-[--muted-fg]">
          ${budget.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
