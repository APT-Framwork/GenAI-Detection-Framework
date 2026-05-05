"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Bookmark, Play, History as HistoryIcon } from "lucide-react";
import { parseHunt, type HuntField } from "@/lib/hunt-grammar";

const HISTORY_KEY = "strix:hunt:history:v1";

const FIELD_TINT: Record<HuntField, { bg: string; text: string; border: string }> = {
  host:      { bg: "bg-strix-cyan/15",  text: "text-[#00666d] dark:text-[#87edf6]",            border: "border-[#00666d]/30 dark:border-[#87edf6]/40" },
  user:      { bg: "bg-emerald-500/15", text: "text-emerald-600 dark:text-emerald-400",        border: "border-emerald-500/30" },
  technique: { bg: "bg-purple-500/15",  text: "text-purple-600 dark:text-purple-400",          border: "border-purple-500/30" },
  time:      { bg: "bg-amber-500/15",   text: "text-amber-600 dark:text-amber-400",            border: "border-amber-500/30" },
  text:      { bg: "bg-slate-500/10",   text: "text-[#00343d] dark:text-[var(--strix-text)]",  border: "border-slate-500/30" },
};

interface QueryBarProps {
  value: string;
  onChange: (q: string) => void;
  onSubmit: (q: string) => void;
  onSave: () => void;
  loading: boolean;
  serverErrors: string[];
}

export function QueryBar({
  value,
  onChange,
  onSubmit,
  onSave,
  loading,
  serverErrors,
}: QueryBarProps) {
  const [history, setHistory] = useState<string[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);

  // Load history (localStorage, last 10).
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(HISTORY_KEY);
      if (raw) setHistory(JSON.parse(raw).slice(0, 10));
    } catch { /* ignore */ }
  }, []);

  // Local parse for pill rendering and inline error underlines.
  const parsed = useMemo(() => parseHunt(value), [value]);
  const allErrors = [...parsed.errors, ...serverErrors];

  const pushHistory = (q: string) => {
    const cleaned = q.trim();
    if (!cleaned) return;
    setHistory((prev) => {
      const next = [cleaned, ...prev.filter((p) => p !== cleaned)].slice(0, 10);
      try {
        window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
      } catch { /* ignore */ }
      return next;
    });
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onSubmit(value);
      pushHistory(value);
      setHistoryOpen(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#497f8b] dark:text-[var(--strix-text-muted)]" />
        <input
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKey}
          spellCheck={false}
          placeholder='try   host:db-cluster-7   technique:T1059   time:1h   "free text"'
          className="w-full pl-10 pr-[200px] py-2.5 rounded-lg bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] text-[13px] font-mono text-[#00343d] dark:text-[var(--strix-text)] placeholder:text-[#497f8b]/60 focus:outline-none focus:ring-2 focus:ring-strix-primary/30 dark:focus:ring-strix-cyan/40"
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
          <button
            type="button"
            onClick={() => setHistoryOpen((v) => !v)}
            className="p-1.5 rounded text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-card)]"
            title="Recent queries"
          >
            <HistoryIcon className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!value.trim()}
            className="p-1.5 rounded text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-card)] disabled:opacity-40"
            title="Save query"
          >
            <Bookmark className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => {
              onSubmit(value);
              pushHistory(value);
            }}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-[#00666d] dark:bg-[#87edf6] text-[#cffbff] dark:text-[#00343d] hover:opacity-90 disabled:opacity-50"
          >
            <Play className="h-3 w-3" />
            {loading ? "Running…" : "Run"}
          </button>
        </div>

        {historyOpen && history.length > 0 && (
          <div className="absolute right-0 top-full mt-1 z-20 w-[420px] max-h-[280px] overflow-y-auto bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-lg shadow-xl py-1">
            {history.map((h, i) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  onChange(h);
                  setHistoryOpen(false);
                }}
                className="block w-full text-left px-3 py-1.5 text-[11px] font-mono text-[#00343d] dark:text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)] truncate"
              >
                {h}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Parsed-pill preview */}
      {parsed.tokens.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            parsed
          </span>
          {parsed.tokens.map((t, i) => {
            const tint = FIELD_TINT[t.field];
            return (
              <span
                key={i}
                className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border ${tint.bg} ${tint.text} ${tint.border}`}
              >
                <span className="opacity-70 uppercase">{t.field}</span>
                <span>{t.value}</span>
              </span>
            );
          })}
        </div>
      )}

      {/* Errors */}
      {allErrors.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {allErrors.map((e, i) => (
            <span
              key={i}
              className="text-[10px] text-amber-600 dark:text-amber-400 font-mono"
            >
              ⚠ {e}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
