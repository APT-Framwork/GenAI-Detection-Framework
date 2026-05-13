// persisted-notes.tsx — backend-persisted analyst journal per chain.
//
// Each note lists in reverse-chrono. The current user can edit or delete
// their own notes; foreign notes show no controls. Notes that were edited
// after creation show an "(edited)" marker and the relative time.

"use client";

import { useState } from "react";
import {
  useAddChainNote,
  useChainNotes,
  useDeleteChainNote,
  useUpdateChainNote,
  type ChainNote,
} from "@/lib/api/chains";
import { useMe } from "@/lib/api/auth";
import { toast } from "@/lib/toast";
import { Loader2, Pencil, Send, Trash2 } from "lucide-react";

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function wasEdited(n: ChainNote): boolean {
  if (!n.updatedAt) return false;
  // Treat the timestamps as "same" within a 2 s grace window — server-side
  // server_default=NOW() can fire microseconds apart from the row's own
  // created_at, and we don't want every freshly-created note to claim it
  // was edited.
  const cu = Date.parse(n.createdAt);
  const up = Date.parse(n.updatedAt);
  if (!Number.isFinite(cu) || !Number.isFinite(up)) return false;
  return up - cu > 2_000;
}

export function PersistedNotes({ chainId }: { chainId: string }) {
  const { data, isLoading } = useChainNotes(chainId);
  const add = useAddChainNote(chainId);
  const update = useUpdateChainNote(chainId);
  const remove = useDeleteChainNote(chainId);
  const me = useMe();
  const [draft, setDraft] = useState("");

  const submit = async () => {
    const body = draft.trim();
    if (!body) return;
    try {
      await add.mutateAsync(body);
      setDraft("");
      toast.success("Note saved.");
    } catch {
      toast.error("Could not save note.");
    }
  };

  const notes = data?.items ?? [];
  const myUserId = me.data?.userId ?? null;

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
            <NoteRow
              key={n.noteId}
              note={n}
              canModify={myUserId !== null && n.authorUserId === myUserId}
              onUpdate={async (bodyMd) => {
                try {
                  await update.mutateAsync({ noteId: n.noteId, bodyMd });
                  toast.success("Note updated.");
                } catch {
                  toast.error("Could not update note.");
                  throw new Error("update failed");
                }
              }}
              onDelete={async () => {
                try {
                  await remove.mutateAsync(n.noteId);
                  toast.success("Note deleted.");
                } catch {
                  toast.error("Could not delete note.");
                }
              }}
            />
          ))}
        </ol>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Single note row with inline-edit and confirm-then-delete.
// ────────────────────────────────────────────────────────────────────────────

function NoteRow({
  note,
  canModify,
  onUpdate,
  onDelete,
}: {
  note: ChainNote;
  canModify: boolean;
  onUpdate: (bodyMd: string) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note.bodyMd);
  const [saving, setSaving] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const startEdit = () => {
    setDraft(note.bodyMd);
    setEditing(true);
  };
  const cancelEdit = () => {
    setEditing(false);
    setDraft(note.bodyMd);
  };
  const save = async () => {
    const body = draft.trim();
    if (!body || body === note.bodyMd) {
      cancelEdit();
      return;
    }
    setSaving(true);
    try {
      await onUpdate(body);
      setEditing(false);
    } catch {
      // toast handled upstream
    } finally {
      setSaving(false);
    }
  };
  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await onDelete();
    } finally {
      setDeleting(false);
      setConfirmingDelete(false);
    }
  };

  return (
    <li className="border border-[var(--strix-border)] rounded-md px-3 py-2 bg-[var(--strix-bg-deep)]">
      <div className="flex items-center justify-between text-[10px] text-[var(--strix-text-muted)] mb-1 gap-2">
        <span className="font-mono truncate">{note.authorEmail ?? "system"}</span>
        <div className="flex items-center gap-2 shrink-0">
          <span>{fmtTime(note.createdAt)}</span>
          {wasEdited(note) && (
            <span className="italic text-[9px]" title={`edited ${fmtTime(note.updatedAt ?? note.createdAt)}`}>
              (edited)
            </span>
          )}
          {canModify && !editing && !confirmingDelete && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={startEdit}
                className="p-1 rounded hover:bg-[var(--strix-bg-surface)] text-[var(--strix-text-muted)] hover:text-strix-cyan transition-colors"
                title="Edit note"
              >
                <Pencil className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => setConfirmingDelete(true)}
                className="p-1 rounded hover:bg-[var(--strix-bg-surface)] text-[var(--strix-text-muted)] hover:text-rose-500 transition-colors"
                title="Delete note"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>
      </div>

      {editing ? (
        <div className="flex flex-col gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                save();
              } else if (e.key === "Escape") {
                e.preventDefault();
                cancelEdit();
              }
            }}
            rows={Math.max(2, draft.split("\n").length)}
            className="w-full text-[12px] bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] rounded px-2 py-1.5 text-[var(--strix-text)] outline-none focus:border-strix-cyan resize-y"
            autoFocus
          />
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={cancelEdit}
              disabled={saving}
              className="text-[10px] uppercase tracking-wider px-2 py-1 rounded text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={save}
              disabled={saving || !draft.trim() || draft.trim() === note.bodyMd}
              className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-bold px-2.5 py-1 rounded bg-[#00666d] text-white hover:bg-[#005a61] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              Save
            </button>
          </div>
        </div>
      ) : confirmingDelete ? (
        <div className="flex flex-col gap-2">
          <p className="text-[11px] text-rose-500">
            Delete this note? This cannot be undone.
          </p>
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setConfirmingDelete(false)}
              disabled={deleting}
              className="text-[10px] uppercase tracking-wider px-2 py-1 rounded text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirmDelete}
              disabled={deleting}
              className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-bold px-2.5 py-1 rounded bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {deleting ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              Delete
            </button>
          </div>
        </div>
      ) : (
        <p className="text-[12px] text-[var(--strix-text)] whitespace-pre-wrap leading-snug">
          {note.bodyMd}
        </p>
      )}
    </li>
  );
}
