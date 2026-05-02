"use client"

// operator-notes.tsx — per-chain free-form notepad. Stored entirely in
// localStorage keyed by chainId. There's no backend persistence layer
// for notes yet, but having a place to jot during an investigation is
// useful enough that local-only is a real improvement.

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { Save, StickyNote } from "lucide-react"
import { toast } from "@/lib/toast"

interface OperatorNotesProps {
  chainId: string
  className?: string
}

const LS_PREFIX = "strix:notes:"

export function OperatorNotes({ chainId, className }: OperatorNotesProps) {
  const [text, setText] = useState("")
  const [savedAt, setSavedAt] = useState<number | null>(null)

  useEffect(() => {
    if (typeof window === "undefined") return
    try {
      const raw = window.localStorage.getItem(LS_PREFIX + chainId)
      if (raw) {
        const parsed = JSON.parse(raw) as { text: string; savedAt: number }
        setText(parsed.text)
        setSavedAt(parsed.savedAt)
      } else {
        setText("")
        setSavedAt(null)
      }
    } catch { /* ignore */ }
  }, [chainId])

  const onSave = () => {
    if (typeof window === "undefined") return
    const now = Date.now()
    try {
      window.localStorage.setItem(
        LS_PREFIX + chainId,
        JSON.stringify({ text, savedAt: now }),
      )
      setSavedAt(now)
      toast.success("Notes saved locally.")
    } catch {
      toast.error("Could not save notes (localStorage unavailable).")
    }
  }

  return (
    <div className={cn("w-full", className)}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <StickyNote className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
          <h3 className="text-sm font-bold text-[var(--strix-text)]">Operator Notes</h3>
          <span className="text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider">
            local-only
          </span>
        </div>
        <span className="text-[10px] text-[var(--strix-text-muted)] font-mono">
          {savedAt ? `saved ${new Date(savedAt).toLocaleTimeString()}` : "unsaved"}
        </span>
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Investigation notes for chain ${chainId.slice(0, 8)}…`}
        rows={4}
        className="w-full text-[12px] bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] rounded-lg px-3 py-2 text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] outline-none focus:border-strix-cyan resize-y"
      />
      <div className="flex justify-end mt-2">
        <button
          onClick={onSave}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider bg-strix-cyan/10 text-strix-primary dark:text-strix-cyan border border-strix-cyan/30 hover:bg-strix-cyan/20 transition-colors"
        >
          <Save className="h-3.5 w-3.5" />
          Save Notes
        </button>
      </div>
    </div>
  )
}
