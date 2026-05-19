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
BACKEND = [
    ("Python", "python", "#3776AB"),
    ("FastAPI", "fastapi", "#009688"),
    ("Pydantic", "pydantic", "#E92063"),
    ("SQLAlchemy", "sqlalchemy", "#D71F00"),
    ("PostgreSQL", "postgresql", "#4169E1"),
    ("Redis", "redis", "#DC382D"),
    ("PyTorch", "pytorch", "#EE4C2C"),
    ("HuggingFace", "huggingface", "#FFD21E"),
    ("NumPy", "numpy", "#013243"),
    ("pandas", "pandas", "#150458"),
    ("scikitlearn", "scikitlearn", "#F7931E"),
    ("Anthropic", "anthropic", "#191919"),
]

RL = [
    ("PyTorch", "pytorch", "#EE4C2C"),
    ("NumPy", "numpy", "#013243"),
    ("pandas", "pandas", "#150458"),
    ("scikitlearn", "scikitlearn", "#F7931E"),
    ("Matplotlib", None, None),  # no simple-icons entry, use text tile
    ("Gym", None, None),
]

WEB = [
    ("Next.js", "nextdotjs", "#000000"),
    ("React", "react", "#61DAFB"),
    ("TypeScript", "typescript", "#3178C6"),
    ("Tailwind", "tailwindcss", "#06B6D4"),
    ("ReactQuery", "reactquery", "#FF4154"),
    ("Zustand", None, None),
    ("ReactFlow", None, None),
    ("Recharts", None, None),
]

MOBILE = [
    ("Expo", "expo", "#000020"),
    ("ReactNative", "react", "#61DAFB"),
    ("TypeScript", "typescript", "#3178C6"),
    ("ReactQuery", "reactquery", "#FF4154"),
    ("Zustand", None, None),
    ("FCM/Push", "firebase", "#DD2C00"),
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


if __name__ == "__main__":
    print("Generating Chapter 5 logo grids...")
    render_grid(BACKEND, cols=4, out_stem="stack_logos_backend")
    render_grid(RL, cols=6, out_stem="stack_logos_rl")
    render_grid(WEB, cols=4, out_stem="stack_logos_web")
    render_grid(MOBILE, cols=3, out_stem="stack_logos_mobile")
    print("Done.")
