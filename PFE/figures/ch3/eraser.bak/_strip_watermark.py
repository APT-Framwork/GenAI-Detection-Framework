#!/usr/bin/env python3
"""Strip the Eraser free-plan watermark from exported SVGs.

The watermark is two sibling <g> elements near the end of every Eraser
export: one contains a base64 PNG of the Eraser brand logo, the other
contains an inline <svg> with <title>eraser.io</title>. Both are top-level
children of the root <svg>; removing them does not affect the diagram.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent


def find_group_around(svg_text: str, needle_pos: int) -> tuple[int, int] | None:
    """Return (start, end) byte offsets of the <g …>…</g> that encloses needle_pos.

    Walks backwards to find the opening <g, then forward through nested <g>…</g>
    pairs until depth returns to zero.
    """
    start = svg_text.rfind("<g ", 0, needle_pos)
    if start == -1:
        return None
    depth = 0
    i = start
    while i < len(svg_text):
        if svg_text.startswith("<g ", i) or svg_text.startswith("<g>", i):
            depth += 1
            i += 2
        elif svg_text.startswith("</g>", i):
            depth -= 1
            i += 4
            if depth == 0:
                return (start, i)
        else:
            i += 1
    return None


def strip_watermark(svg_text: str) -> tuple[str, int]:
    """Return (cleaned_svg, removed_count)."""
    removed = 0
    # Block 1: the <g> that wraps <title>eraser.io</title>
    title_pos = svg_text.find("<title>eraser.io</title>")
    if title_pos != -1:
        span = find_group_around(svg_text, title_pos)
        if span:
            # Also remove the immediately preceding sibling <g> (the logo PNG)
            prev_end = span[0]
            # Skip whitespace backwards
            j = prev_end - 1
            while j >= 0 and svg_text[j] in " \n\r\t":
                j -= 1
            # Check for </g> right before
            if svg_text[max(0, j - 3):j + 1] == "</g>":
                # find matching <g … that opened it
                prev_close = j + 1
                depth = 1
                k = j - 3
                while k > 0 and depth > 0:
                    if svg_text.startswith("</g>", k):
                        depth += 1
                        k -= 1
                    elif svg_text.startswith("<g ", k) or svg_text.startswith("<g>", k):
                        depth -= 1
                        if depth == 0:
                            break
                        k -= 1
                    else:
                        k -= 1
                if depth == 0:
                    # Remove [k, span[1])
                    svg_text = svg_text[:k] + svg_text[span[1]:]
                    removed = 2
                    return svg_text, removed
            # Fallback: remove just the title block
            svg_text = svg_text[:span[0]] + svg_text[span[1]:]
            removed = 1
    return svg_text, removed


def main() -> int:
    files = sorted(HERE.glob("*.svg"))
    if not files:
        print("no SVGs found", file=sys.stderr)
        return 1
    for f in files:
        original = f.read_text(encoding="utf-8")
        cleaned, n = strip_watermark(original)
        if n == 0:
            print(f"  no watermark found  {f.name}")
            continue
        f.write_text(cleaned, encoding="utf-8")
        saved = len(original) - len(cleaned)
        print(f"  stripped {n} block(s)  -{saved:>6} bytes  {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
