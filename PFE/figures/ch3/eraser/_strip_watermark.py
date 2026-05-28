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


LOGO_IMG_RE = re.compile(r'<image[^>]*width="100"[^>]*height="29"[^>]*>')

VIEWBOX_RE = re.compile(r'(viewBox=")(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)(")')
ROOT_HEIGHT_RE = re.compile(r'(<svg[^>]*\bheight=")(\d+(?:\.\d+)?)(")')
BG_RECT_RE = re.compile(r'(<rect x="0" y="0" width="\d+(?:\.\d+)?" height=")(\d+(?:\.\d+)?)(" fill="#[0-9a-fA-F]{3,6}"[^>]*>)')
TRANSLATE_ROTATE_RE = re.compile(r'translate\(\s*[0-9.]+\s+([0-9.]+)\s*\)\s*rotate\(\s*0\s+[0-9.]+\s+([0-9.]+)\s*\)')


def max_content_y(svg_text: str) -> float | None:
    """Return the largest y-bottom of any rotation-anchored content block."""
    bottoms = []
    for m in TRANSLATE_ROTATE_RE.finditer(svg_text):
        ty = float(m.group(1))
        half_h = float(m.group(2))
        bottoms.append(ty + 2 * half_h)
    return max(bottoms) if bottoms else None


def trim_viewbox(svg_text: str, margin: float = 20.0) -> tuple[str, float]:
    """Shrink root viewBox + height attr + background rect to content + margin.

    Returns (new_text, trimmed_px). trimmed_px == 0 if nothing changed.
    """
    max_y = max_content_y(svg_text)
    if max_y is None:
        return svg_text, 0.0
    target = round(max_y + margin, 1)
    vb = VIEWBOX_RE.search(svg_text)
    if not vb:
        return svg_text, 0.0
    current_h = float(vb.group(5))
    if target >= current_h:
        return svg_text, 0.0
    trimmed = current_h - target
    new_vb = f"{vb.group(1)}{vb.group(2)} {vb.group(3)} {vb.group(4)} {target}{vb.group(6)}"
    svg_text = svg_text[:vb.start()] + new_vb + svg_text[vb.end():]
    # Update <svg ... height="..."> on the root element (only the first match — the root)
    rh = ROOT_HEIGHT_RE.search(svg_text)
    if rh:
        svg_text = svg_text[:rh.start()] + f"{rh.group(1)}{target}{rh.group(3)}" + svg_text[rh.end():]
    # Update the page-background rect's height
    bg = BG_RECT_RE.search(svg_text)
    if bg:
        svg_text = svg_text[:bg.start()] + f"{bg.group(1)}{target}{bg.group(3)}" + svg_text[bg.end():]
    return svg_text, trimmed


def strip_watermark(svg_text: str) -> tuple[str, int]:
    """Return (cleaned_svg, removed_count)."""
    removed = 0
    # Block 1: the <g> that wraps <title>eraser.io</title>
    title_pos = svg_text.find("<title>eraser.io</title>")
    if title_pos != -1:
        span = find_group_around(svg_text, title_pos)
        if span:
            svg_text = svg_text[:span[0]] + svg_text[span[1]:]
            removed += 1
    # Block 2: the <g> that wraps the 100x29 Eraser logo PNG <image>
    m = LOGO_IMG_RE.search(svg_text)
    if m:
        span = find_group_around(svg_text, m.start())
        if span:
            svg_text = svg_text[:span[0]] + svg_text[span[1]:]
            removed += 1
    return svg_text, removed


def main() -> int:
    files = sorted(HERE.glob("*.svg"))
    if not files:
        print("no SVGs found", file=sys.stderr)
        return 1
    for f in files:
        original = f.read_text(encoding="utf-8")
        cleaned, n = strip_watermark(original)
        cleaned, trimmed_px = trim_viewbox(cleaned)
        if n == 0 and trimmed_px == 0:
            print(f"  no changes        {f.name}")
            continue
        f.write_text(cleaned, encoding="utf-8")
        saved = len(original) - len(cleaned)
        print(f"  stripped={n}  viewbox-trim={trimmed_px:>5.0f}px  -{saved:>6} bytes  {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
