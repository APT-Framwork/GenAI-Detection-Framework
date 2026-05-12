// persisted-notes.tsx — backend-persisted analyst journal per chain.
//
// Append-only: each submit creates a new note row. Lists in reverse-chrono.
// Replaces the localStorage scratchpad in OperatorNotes.

"use client";

import { useState } from "react";
import { useAddChainNote, useChainNotes } from "@/lib/api/chains";
import { toast } from "@/lib/toast";
import { Loader2, Send } from "lucide-react";

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function PersistedNotes({ chainId }: { chainId: string }) {
  const { data, isLoading } = useChainNotes(chainId);
  const add = useAddChainNote(chainId);
  const [draft, setDraft] = useState("");

  const submit = async () => {
    const body = draft.trim();
    if (!body) return;
    try {
      await add.mutateAsync(body);
      setDraft("");
      toast.success("Note saved.");
    } catch (e) {
      toast.error("Could not save note.");
    }
  };

  const notes = data?.items ?? [];

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-sm font-bold text-[var(--strix-text)]">Operator Notes</h3>
        <span className="text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider">
          persisted · {notes.length}
        </span>
      </div>

      <div className="flex gap-2 mb-3">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Add an investigation note… (⌘↵ to send)"
          rows={2}
          className="flex-1 text-[12px] bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] rounded-lg px-3 py-2 text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] outline-none focus:border-strix-cyan resize-y"
        />
        <button
          type="button"
          disabled={!draft.trim() || add.isPending}
          onClick={submit}
          className="self-start flex items-center gap-1 px-3 py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-md bg-[#00666d] text-white hover:bg-[#005a61] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {add.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Send className="h-3 w-3" />
          )}
          Add
        </button>
      </div>

      {isLoading ? (
        <p className="text-[11px] text-[var(--strix-text-muted)] italic">Loading…</p>
      ) : notes.length === 0 ? (
        <p className="text-[11px] text-[var(--strix-text-muted)] italic">
          No notes yet. Add the first observation.
        </p>
      ) : (
        <ol className="space-y-2 max-h-[260px] overflow-y-auto pr-1">
          {notes.map((n) => (
            <li
              key={n.noteId}
              className="border border-[var(--strix-border)] rounded-md px-3 py-2 bg-[var(--strix-bg-deep)]"
            >
              <div className="flex items-center justify-between text-[10px] text-[var(--strix-text-muted)] mb-1">
                <span className="font-mono">{n.authorEmail ?? "system"}</span>
                <span>{fmtTime(n.createdAt)}</span>
              </div>
              <p className="text-[12px] text-[var(--strix-text)] whitespace-pre-wrap leading-snug">
                {n.bodyMd}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
