// tag-picker.tsx — inline tag list + add input. Backed by /chains/{id}/tags.

"use client";

import { useState } from "react";
import {
  useAddChainTag,
  useChainTags,
  useRemoveChainTag,
} from "@/lib/api/chains";
import { TagChip } from "@/components/ui/tag-chip";
import { toast } from "@/lib/toast";
import { Plus } from "lucide-react";

export function TagPicker({ chainId }: { chainId: string }) {
  const { data } = useChainTags(chainId);
  const add = useAddChainTag(chainId);
  const remove = useRemoveChainTag(chainId);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);

  const submit = async () => {
    const v = draft.trim();
    if (!v) {
      setEditing(false);
      return;
    }
    try {
      await add.mutateAsync(v);
      setDraft("");
      setEditing(false);
    } catch {
      toast.error("Could not add tag.");
    }
  };

  const items = data?.items ?? [];

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {items.map((t) => (
        <TagChip
          key={t.tagId}
          name={t.name}
          onRemove={async () => {
            try {
              await remove.mutateAsync(t.name);
            } catch {
              toast.error("Could not remove tag.");
            }
          }}
        />
      ))}
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") {
              setEditing(false);
              setDraft("");
            }
          }}
          onBlur={submit}
          placeholder="tag…"
          className="w-20 text-[10px] font-mono uppercase tracking-wider bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] rounded px-1.5 py-0.5 text-[var(--strix-text)] outline-none focus:border-strix-cyan"
        />
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="inline-flex items-center gap-0.5 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-dashed border-[var(--strix-border)] text-[var(--strix-text-muted)] hover:border-strix-cyan hover:text-strix-cyan"
        >
          <Plus className="h-2.5 w-2.5" />
          Tag
        </button>
      )}
    </div>
  );
}
