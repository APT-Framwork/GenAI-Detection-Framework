// Tag chip primitive — small rounded label, optional remove button.

import { X } from "lucide-react";
import { cn } from "@/lib/utils";

// Stable hash-to-colour mapping. Same tag name always gets the same
// colour without burning a column on every row of `tags`.
const PALETTE = [
  "bg-[#87edf6]/20 text-[#00666d] border-[#87edf6]/40",
  "bg-[#c44]/15 text-[#c44] border-[#c44]/40",
  "bg-[#d80]/15 text-[#d80] border-[#d80]/40",
  "bg-[#2a8]/15 text-[#2a8] border-[#2a8]/40",
  "bg-[#a4c]/15 text-[#a4c] border-[#a4c]/40",
  "bg-[#497f8b]/15 text-[#497f8b] border-[#497f8b]/40",
];

function colourFor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

interface TagChipProps {
  name: string;
  onRemove?: () => void;
  className?: string;
}

export function TagChip({ name, onRemove, className }: TagChipProps) {
  const colour = colourFor(name);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider",
        "px-1.5 py-0.5 rounded border",
        colour,
        className,
      )}
    >
      {name}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="hover:opacity-70 -mr-0.5"
          aria-label={`remove tag ${name}`}
        >
          <X className="h-2.5 w-2.5" />
        </button>
      )}
    </span>
  );
}
