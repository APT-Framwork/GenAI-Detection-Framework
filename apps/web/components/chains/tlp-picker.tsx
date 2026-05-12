// tlp-picker.tsx — clickable TLP badge → opens a small dropdown of TLP
// levels. Selecting one PATCHes /chains/{id}/tlp and invalidates the
// chain's TLP + activity queries.

"use client";

import { useEffect, useRef, useState } from "react";
import { useChainTlp, useSetChainTlp, type Tlp } from "@/lib/api/chains";
import { TlpBadge } from "@/components/ui/tlp-badge";
import { toast } from "@/lib/toast";

const LEVELS: Tlp[] = ["clear", "green", "amber", "amber+strict", "red"];

export function TlpPicker({ chainId }: { chainId: string }) {
  const { data } = useChainTlp(chainId);
  const setTlp = useSetChainTlp(chainId);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const current = data?.tlp ?? "amber";

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!open) return;
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const pick = async (lvl: Tlp) => {
    setOpen(false);
    if (lvl === current) return;
    try {
      await setTlp.mutateAsync(lvl);
      toast.success(`TLP set to ${lvl}`);
    } catch {
      toast.error("Could not update TLP.");
    }
  };

  return (
    <div ref={wrapRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="cursor-pointer hover:opacity-90 transition-opacity"
        title="Change TLP marking"
      >
        <TlpBadge value={current} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-md shadow-lg py-1 min-w-[160px]">
          {LEVELS.map((lvl) => (
            <button
              key={lvl}
              type="button"
              onClick={() => pick(lvl)}
              className="w-full text-left px-2 py-1 hover:bg-[var(--strix-bg-surface)] flex items-center gap-2"
            >
              <TlpBadge value={lvl} />
              {lvl === current && (
                <span className="ml-auto text-[10px] text-[var(--strix-text-muted)]">
                  current
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
