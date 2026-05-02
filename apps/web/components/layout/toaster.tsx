"use client";

import { useToastStore, type ToastKind } from "@/lib/toast";
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

const ICONS: Record<ToastKind, typeof CheckCircle2> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: AlertCircle,
};

const STYLES: Record<ToastKind, string> = {
  info: "border-cyan-500/40 bg-cyan-500/10 text-cyan-700 dark:text-cyan-200",
  success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-200",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-200",
  error: "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-200",
};

export function Toaster() {
  const items = useToastStore((s) => s.items);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {items.map((t) => {
        const Icon = ICONS[t.kind];
        return (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-start gap-3 rounded-xl border px-4 py-3 shadow-lg backdrop-blur-md min-w-[260px] max-w-[420px] animate-slide-up-in",
              STYLES[t.kind],
            )}
            role="status"
          >
            <Icon className="h-4 w-4 mt-0.5 shrink-0" />
            <div className="text-[12px] font-medium leading-snug flex-1">{t.message}</div>
            <button
              onClick={() => dismiss(t.id)}
              className="opacity-70 hover:opacity-100 transition-opacity"
              aria-label="dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
