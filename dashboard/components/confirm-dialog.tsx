"use client";

import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  destructive?: boolean;
}

export function ConfirmDialog({
  open,
  message,
  confirmLabel = "Confirm",
  onConfirm,
  onCancel,
  destructive = false,
}: ConfirmDialogProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.6)" }}
          onClick={onCancel}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="card-base p-6 max-w-sm w-full mx-4 flex flex-col gap-4"
            style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.5)" }}
          >
            <div className="flex items-start gap-3">
              <div
                className="flex items-center justify-center w-8 h-8 rounded-md shrink-0"
                style={{ background: destructive ? "rgba(239,68,68,0.12)" : "rgba(245,158,11,0.12)" }}
              >
                <AlertTriangle
                  className="w-4 h-4"
                  style={{ color: destructive ? "#ef4444" : "var(--amber)" }}
                  strokeWidth={1.8}
                />
              </div>
              <p className="text-sm leading-relaxed pt-0.5" style={{ color: "var(--foreground)" }}>
                {message}
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={onCancel}
                className="px-3 py-1.5 rounded text-xs font-600 transition-colors"
                style={{
                  background: "rgba(255,255,255,0.05)",
                  color: "var(--muted-fg)",
                  border: "1px solid var(--border)",
                }}
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                className="px-3 py-1.5 rounded text-xs font-600 transition-colors"
                style={{
                  background: destructive ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.12)",
                  color: destructive ? "#ef4444" : "var(--amber)",
                  border: `1px solid ${destructive ? "rgba(239,68,68,0.3)" : "rgba(245,158,11,0.3)"}`,
                }}
              >
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
