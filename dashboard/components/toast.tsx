"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle, AlertTriangle, X } from "lucide-react";

interface ToastProps {
  message: string;
  show: boolean;
  onClose: () => void;
  type?: "success" | "error";
}

export function Toast({ message, show, onClose, type = "success" }: ToastProps) {
  useEffect(() => {
    if (!show) return;
    const t = setTimeout(onClose, 3000);
    return () => clearTimeout(t);
  }, [show, onClose]);

  const Icon = type === "error" ? AlertTriangle : CheckCircle;
  const iconColor = type === "error" ? "#ef4444" : "#22c55e";

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.95 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-lg card-base"
          style={{ boxShadow: "0 4px 24px rgba(0,0,0,0.4)" }}
        >
          <Icon className="w-4 h-4 shrink-0" style={{ color: iconColor }} strokeWidth={2} />
          <span className="text-sm text-[--foreground]">{message}</span>
          <button
            onClick={onClose}
            className="ml-1 text-[--muted-fg] hover:text-[--foreground] transition-colors"
            aria-label="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
