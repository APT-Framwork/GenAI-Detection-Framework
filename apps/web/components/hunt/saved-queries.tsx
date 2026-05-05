"use client";

import { Bookmark, Trash2 } from "lucide-react";
import {
  useSavedQueries,
  useDeleteSavedQuery,
  type SavedQuery,
} from "@/lib/api/hunt";

interface SavedQueriesProps {
  onRun: (q: string) => void;
}

export function SavedQueries({ onRun }: SavedQueriesProps) {
  const list = useSavedQueries();
  const del = useDeleteSavedQuery();

  const items: SavedQuery[] = list.data?.items ?? [];

  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-lg p-4 sticky top-4">
      <div className="flex items-center gap-2 mb-3">
        <Bookmark className="h-3.5 w-3.5 text-[#00666d] dark:text-[#87edf6]" />
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-[#00343d] dark:text-[var(--strix-text)]">
          Saved Queries
        </h3>
        <span className="ml-auto text-[10px] tabular-nums text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {items.length}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="text-[10px] italic text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          Save a query (bookmark icon in the bar) to pin it here.
        </p>
      ) : (
        <ul className="space-y-1">
          {items.map((s) => (
            <li
              key={s.savedId}
              className="group flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[var(--strix-bg-surface)]/50"
            >
              <button
                type="button"
                onClick={() => onRun(s.q)}
                className="flex-1 min-w-0 text-left"
              >
                <p className="text-[11px] font-semibold text-[#00343d] dark:text-[var(--strix-text)] truncate">
                  {s.name}
                </p>
                <p className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] truncate">
                  {s.q}
                </p>
              </button>
              <button
                type="button"
                onClick={() => del.mutate(s.savedId)}
                disabled={del.isPending}
                className="opacity-0 group-hover:opacity-100 text-[#497f8b] hover:text-[#b31b25] disabled:opacity-30 transition-opacity"
                title="Delete saved query"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
