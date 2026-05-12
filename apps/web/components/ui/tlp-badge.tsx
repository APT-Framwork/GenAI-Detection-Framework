// TLP badge primitive (FIRST.org Traffic Light Protocol 2.0).
//
// Pure cosmetic component — for clickable / editable TLP, wrap with the
// picker dropdown in features/chains/tlp-picker.tsx. Colours follow the
// FIRST spec where applicable; amber-strict uses the same swatch as
// amber with a small `+` glyph.

import { cn } from "@/lib/utils";

export type Tlp = "clear" | "green" | "amber" | "amber+strict" | "red";

const TLP_STYLES: Record<Tlp, string> = {
  // White text on dark background per FIRST guidance; opacity tuned
  // for the dashboard's mid-cyan palette.
  clear: "bg-[#777] text-white",
  green: "bg-[#2a8] text-white",
  amber: "bg-[#d80] text-white",
  "amber+strict": "bg-[#b60] text-white",
  red: "bg-[#c44] text-white",
};

export function TlpBadge({ value, className }: { value: Tlp; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center text-[9px] uppercase font-bold tracking-wider",
        "px-1.5 py-0.5 rounded select-none",
        TLP_STYLES[value],
        className,
      )}
      title={`TLP:${value.toUpperCase()} — FIRST Traffic Light Protocol 2.0`}
    >
      TLP:{value}
    </span>
  );
}
