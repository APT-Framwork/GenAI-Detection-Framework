"""
Generate logo-grid figures for Chapter 5:
  FIG 5.3  stack_logos_backend  (Python + ML stack)
  FIG 5.4  stack_logos_rl       (RL training stack)
  FIG 5.5  stack_logos_web      (Next.js stack)
  FIG 5.6  stack_logos_mobile   (Expo / RN stack)

Pulls SVGs from simpleicons CDN, rasterises to a uniform tile, lays them out
in a grid with the library name underneath, and saves PNG + PDF.

Run: python3 make_logo_grids.py
"""
from __future__ import annotations

import io
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from PIL import Image

OUT_DIR = Path(__file__).parent
CDN = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg"
CACHE = OUT_DIR / "_cache"
CACHE.mkdir(exist_ok=True)

plt.rcParams.update(
    {"font.family": "serif", "font.size": 10, "pdf.fonttype": 42, "ps.fonttype": 42}
)

# (label shown in figure, simpleicons slug, hex tint or None to use brand color)
# Each stack is now a list of (category_name, entries) so the renderer can group
# tiles by architectural layer instead of mixing everything into one flat grid.

BACKEND_GROUPED = [
    ("Backend & API", [
        ("Python",      "python",     "#3776AB"),
        ("FastAPI",     "fastapi",    "#009688"),
        ("Pydantic",    "pydantic",   "#E92063"),
        ("SQLAlchemy",  "sqlalchemy", "#D71F00"),
    ]),
    ("Persistence", [
        ("PostgreSQL",  "postgresql", "#4169E1"),
        ("Redis",       "redis",      "#DC382D"),
    ]),
    ("Classical ML & data", [
        ("scikit-learn","scikitlearn","#F7931E"),
        ("NumPy",       "numpy",      "#013243"),
        ("pandas",      "pandas",     "#150458"),
    ]),
    ("DL and RL", [
        ("PyTorch",     "pytorch",    "#EE4C2C"),
        ("HuggingFace", "huggingface","#FFD21E"),
    ]),
]

WEB_GROUPED = [
    ("Framework & language", [
        ("Next.js",     "nextdotjs",  "#000000"),
        ("React",       "react",      "#61DAFB"),
        ("TypeScript",  "typescript", "#3178C6"),
    ]),
    ("Styling", [
        ("Tailwind",    "tailwindcss","#06B6D4"),
    ]),
    ("State & data", [
        ("TanStack Query","reactquery","#FF4154"),
    ]),
]

MOBILE_GROUPED = [
    ("Framework & language", [
        ("Expo",        "expo",       "#000020"),
        ("React Native","react",      "#61DAFB"),
        ("TypeScript",  "typescript", "#3178C6"),
    ]),
    ("State & data", [
        ("TanStack Query","reactquery","#FF4154"),
    ]),
    ("Notifications", [
        ("FCM",         "firebase",   "#DD2C00"),
    ]),
]


def fetch_svg(slug: str) -> bytes:
    cache_path = CACHE / f"{slug}.svg"
    if cache_path.exists():
        return cache_path.read_bytes()
    url = CDN.format(slug=slug)
    print(f"  fetching {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = resp.read()
    cache_path.write_bytes(data)
    time.sleep(0.4)  # avoid CDN rate-limiting on rapid sequential fetches
    return data


def tinted_png(svg_bytes: bytes, hex_color: str, size_px: int = 256) -> Image.Image:
    svg_text = svg_bytes.decode("utf-8")
    if "<svg" in svg_text and 'fill="' not in svg_text.split(">", 1)[0]:
        svg_text = svg_text.replace("<svg", f'<svg fill="{hex_color}"', 1)
    proc = subprocess.run(
        ["rsvg-convert", "-w", str(size_px), "-h", str(size_px), "-b", "white"],
        input=svg_text.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return Image.open(io.BytesIO(proc.stdout)).convert("RGBA")


def text_tile(label: str, size_px: int = 256) -> Image.Image:
    """Fallback tile when the library has no simple-icons entry."""
    img = Image.new("RGBA", (size_px, size_px), (245, 245, 245, 255))
    # Use matplotlib to render text into an image, then composite
    fig, ax = plt.subplots(figsize=(size_px / 100, size_px / 100), dpi=100)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(
        0.5,
        0.5,
        label,
        ha="center",
        va="center",
        fontsize=22,
        weight="bold",
        color="#444",
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1, facecolor="#f5f5f5")
    plt.close(fig)
    return Image.open(buf).convert("RGBA").resize((size_px, size_px))


def render_grid(
    entries: Iterable[tuple[str, str | None, str | None]],
    cols: int,
    out_stem: str,
    title: str | None = None,
) -> None:
    items = list(entries)
    rows = -(-len(items) // cols)  # ceil
    tile_w = 2.2  # inches per tile
    fig_w = cols * tile_w
    fig_h = rows * (tile_w + 0.4) + (0.5 if title else 0.1)

    fig, axes = plt.subplots(rows, cols, figsize=(fig_w, fig_h))
    if rows == 1:
        axes = [axes] if cols == 1 else list(axes)
    else:
        axes = [a for row in axes for a in row]

    for ax in axes:
        ax.axis("off")

    for ax, (label, slug, hex_color) in zip(axes, items):
        try:
            if slug:
                img = tinted_png(fetch_svg(slug), hex_color or "#222")
            else:
                img = text_tile(label)
            ab = AnnotationBbox(
                OffsetImage(img, zoom=0.20),
                (0.5, 0.65),
                frameon=False,
            )
            ax.add_artist(ab)
            ax.text(0.5, 0.05, label, ha="center", va="bottom", fontsize=10)
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN: {label} failed -> {exc}; falling back to text tile")
            img = text_tile(label)
            ab = AnnotationBbox(OffsetImage(img, zoom=0.20), (0.5, 0.65), frameon=False)
            ax.add_artist(ab)
            ax.text(0.5, 0.05, label, ha="center", va="bottom", fontsize=10)

    if title:
        fig.suptitle(title, fontsize=12, y=0.99)

    fig.tight_layout()
    out_pdf = OUT_DIR / f"{out_stem}.pdf"
    out_png = OUT_DIR / f"{out_stem}.png"
    fig.savefig(out_pdf, bbox_inches="tight")
    fig.savefig(out_png, bbox_inches="tight", dpi=200)
    print(f"  wrote {out_pdf.name} (and .png)")
    plt.close(fig)


def render_grouped(
    groups: list[tuple[str, list[tuple[str, str | None, str | None]]]],
    cols: int,
    out_stem: str,
) -> None:
    """Render a stack as vertically stacked category bands. Each category gets
    a small bold header row above a row of tiles. Output is one PNG + PDF.

    `groups`: list of (category_name, entries). Within each category, entries
    flow into as many tile rows as needed to fit `cols` per row.
    """
    # Pre-compute how many tile rows each category needs.
    cat_layout = [
        (name, entries, -(-len(entries) // cols))  # ceil(len / cols)
        for name, entries in groups
    ]
    total_tile_rows = sum(r for _, _, r in cat_layout)
    n_categories = len(cat_layout)

    tile_w_in = 1.6
    tile_h_in = 1.25
    header_h_in = 0.36
    inner_pad_in = 0.08  # small breathing room between categories

    fig_w = cols * tile_w_in
    fig_h = (
        total_tile_rows * tile_h_in
        + n_categories * header_h_in
        + (n_categories - 1) * inner_pad_in
        + 0.20
    )

    fig = plt.figure(figsize=(fig_w, fig_h))

    # Iterate top-down. y_cursor measured in figure-fraction, top = 1.0.
    y_cursor = 1.0
    for cat_idx, (name, entries, tile_rows) in enumerate(cat_layout):
        # Header band
        header_frac = header_h_in / fig_h
        # Section title, left-aligned, bold, with a thin underline rule
        header_y_center = y_cursor - header_frac * 0.55
        fig.text(
            0.015,
            header_y_center,
            name,
            fontsize=11.5,
            weight="bold",
            color="#1f2937",
            va="center",
            ha="left",
        )
        # Subtle rule under the header
        rule_y = y_cursor - header_frac + 0.004
        rule_ax = fig.add_axes((0.015, rule_y, 0.97, 0.0015))
        rule_ax.axhline(0.5, color="#9ca3af", linewidth=0.6)
        rule_ax.axis("off")
        y_cursor -= header_frac

        # Tile band: tile_rows rows × cols cols.
        single_tile_h_frac = tile_h_in / fig_h
        single_tile_w_frac = 0.97 / cols
        left_margin = 0.015

        for idx, (label, slug, hex_color) in enumerate(entries):
            r = idx // cols  # tile-row index within this category
            c = idx % cols
            x_left = left_margin + c * single_tile_w_frac
            y_bottom = y_cursor - (r + 1) * single_tile_h_frac

            ax = fig.add_axes(
                (x_left, y_bottom, single_tile_w_frac, single_tile_h_frac)
            )
            ax.axis("off")
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)

            try:
                if slug:
                    img = tinted_png(fetch_svg(slug), hex_color or "#222")
                else:
                    img = text_tile(label)
            except Exception as exc:  # noqa: BLE001
                print(f"  WARN: {label} failed -> {exc}; falling back to text")
                img = text_tile(label)

            ab = AnnotationBbox(
                OffsetImage(img, zoom=0.10),
                (0.5, 0.62),
                frameon=False,
            )
            ax.add_artist(ab)
            ax.text(0.5, 0.06, label, ha="center", va="bottom", fontsize=9)

        y_cursor -= tile_rows * single_tile_h_frac
        if cat_idx < n_categories - 1:
            y_cursor -= inner_pad_in / fig_h

    out_pdf = OUT_DIR / f"{out_stem}.pdf"
    out_png = OUT_DIR / f"{out_stem}.png"
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    fig.savefig(out_png, bbox_inches="tight", dpi=200, facecolor="white")
    print(f"  wrote {out_pdf.name} (and .png)")
    plt.close(fig)


if __name__ == "__main__":
    print("Generating Chapter 4 logo grids (category-grouped)...")
    render_grouped(BACKEND_GROUPED, cols=4, out_stem="stack_logos_backend")
    render_grouped(WEB_GROUPED,     cols=3, out_stem="stack_logos_web")
    render_grouped(MOBILE_GROUPED,  cols=3, out_stem="stack_logos_mobile")
    print("Done.")
