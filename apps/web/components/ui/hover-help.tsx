// -----------------------------------------------------------------------------
// hover-help.tsx — IDE-style hover tooltip for explaining dashboard metrics.
//
// Wraps a trigger element. On hover/focus, an absolutely-positioned popover
// fades in with an optional title + body. Styled to match the rest of the
// Strix dark UI (card bg, soft cyan border, mono labels).
//
// No portal: parents on the analytics dashboard don't clip via overflow, so
// a position:absolute popover is enough. If we ever introduce an overflow
// boundary above one of these triggers, swap in a portal here without
// changing call-sites.
// -----------------------------------------------------------------------------

"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface HoverHelpProps {
  /** Bold heading at the top of the popover. Optional. */
  title?: ReactNode;
  /** Main body — string or rich JSX. */
  body: ReactNode;
  /** Optional smaller footnote, e.g. "stays event-time only". */
  footnote?: ReactNode;
  /** Which side of the trigger the popover sits on. */
  side?: "top" | "bottom";
  /** Horizontal alignment relative to the trigger. */
  align?: "start" | "center" | "end";
  /** Popover width in px. Default 280. */
  width?: number;
  /** Extra class on the trigger wrapper. */
  className?: string;
  /** Render as a block wrapper that stretches to fill the parent (default
   *  is inline so badges keep their natural width). Use this when wrapping
   *  card-style triggers (e.g. Stat tiles) that should fill a grid cell. */
  block?: boolean;
  /** The trigger — usually a badge / number / icon. */
  children: ReactNode;
}

export function HoverHelp({
  title,
  body,
  footnote,
  side = "top",
  align = "center",
  width = 280,
  className,
  block = false,
  children,
}: HoverHelpProps) {
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = useId();

  const show = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpen(true);
  };
  // Brief grace period so the popover doesn't flicker out when the cursor
  // crosses a 1-px gap between trigger and panel — useful when the popover
  // contains links the user wants to click without losing the panel.
  const hide = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpen(false), 80);
  };

  const sideCls =
    side === "top"
      ? "bottom-[calc(100%+6px)]"
      : "top-[calc(100%+6px)]";
  const alignCls =
    align === "start"
      ? "left-0"
      : align === "end"
        ? "right-0"
        : "left-1/2 -translate-x-1/2";

  return (
    <span
      className={cn(
        "relative",
        block ? "flex w-full" : "inline-flex",
        className,
      )}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <span
        aria-describedby={open ? id : undefined}
        className={cn(
          "items-center cursor-help",
          block ? "flex w-full" : "inline-flex",
        )}
        tabIndex={0}
      >
        {children}
      </span>
      {open && (
        <span
          id={id}
          role="tooltip"
          // Keep the popover non-clickable so hovering its content doesn't
          // interfere with hover-out detection on the trigger; pointer-events
          // off also avoids covering nearby triggers.
          className={cn(
            "absolute z-50 pointer-events-none",
            sideCls,
            alignCls,
          )}
          style={{ width }}
        >
          <span
            className={cn(
              "block rounded-lg border bg-[#0b1416] dark:bg-[#0b1416]",
              "border-[rgba(0,242,255,0.22)]",
              "shadow-[0_8px_28px_-12px_rgba(0,0,0,0.7),0_0_0_1px_rgba(0,242,255,0.05)]",
              "p-3 text-left animate-tooltip-in",
            )}
          >
            {title && (
              <span className="block text-[11px] font-bold tracking-wide text-strix-cyan dark:text-strix-cyan font-heading mb-1.5">
                {title}
              </span>
            )}
            <span className="block text-[11px] leading-snug text-[var(--strix-text)] [&_code]:font-mono [&_code]:text-[10px] [&_code]:px-1 [&_code]:py-[1px] [&_code]:rounded [&_code]:bg-white/5 [&_code]:text-strix-cyan [&_strong]:text-strix-cyan [&_strong]:font-semibold">
              {body}
            </span>
            {footnote && (
              <span className="block mt-2 pt-2 border-t border-[rgba(128,182,195,0.15)] text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)]">
                {footnote}
              </span>
            )}
          </span>
        </span>
      )}
    </span>
  );
}
