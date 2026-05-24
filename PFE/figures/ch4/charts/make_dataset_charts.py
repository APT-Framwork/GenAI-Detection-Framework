"""
Generate FIG 5.10 (binary class donut) and FIG 5.11 (per-MITRE-tactic bars)
for Chapter 5 of the PFE report.

FIG 5.10 source: apps/models/labels.parquet (ground truth)
FIG 5.11 source: docs/lab/CALDERA_MITRE_SIMULATION_GUIDE.md (lines 22-39)

Run: python3 make_dataset_charts.py
Outputs: dataset_class_split.pdf, dataset_tactic_bars.pdf
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[5]
LABELS_PATH = REPO_ROOT / "apps" / "models" / "labels.parquet"
OUT_DIR = Path(__file__).parent

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def fig_5_10_class_split() -> None:
    df = pd.read_parquet(LABELS_PATH)
    counts = df["malicious"].value_counts().sort_index()
    benign, malicious = int(counts.loc[0]), int(counts.loc[1])
    total = benign + malicious

    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    colors = ["#3B7DD8", "#E04B4B"]
    sizes = [benign, malicious]
    labels = [
        f"Benign\n{benign:,} ({benign / total:.1%})",
        f"Malicious\n{malicious:,} ({malicious / total:.1%})",
    ]
    wedges, _ = ax.pie(
        sizes,
        colors=colors,
        startangle=90,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
    )
    ax.text(
        0,
        0,
        f"{total:,}\nalerts",
        ha="center",
        va="center",
        fontsize=15,
        weight="bold",
    )
    ax.legend(
        wedges,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.05),
        ncol=2,
        frameon=False,
        fontsize=10,
    )
    ax.set_aspect("equal")
    fig.tight_layout()
    out = OUT_DIR / "dataset_class_split.pdf"
    fig.savefig(out, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=200)
    print(f"  wrote {out.name} (and .png)")
    plt.close(fig)


# From docs/lab/CALDERA_MITRE_SIMULATION_GUIDE.md:22-39
TACTIC_COUNTS = [
    ("Defense Evasion", "S5", 18124),
    ("Privilege Escalation", "S4", 17164),
    ("Initial Access", "S3", 16624),
    ("Discovery", "S7", 14058),
    ("Impact", "S7", 2868),
    ("Persistence", "S5", 1709),
    ("Execution", "S4", 1655),
    ("Reconnaissance", "S1", 643),
    ("Lateral Movement", "S5", 240),
    ("Credential Access", "S7", 35),
    ("Collection", "S7", 3),
    ("Command & Control", "S6", 2),
]

CKC_COLORS = {
    "S1": "#6B5DD3",
    "S3": "#3B7DD8",
    "S4": "#22A699",
    "S5": "#F2BE22",
    "S6": "#E08036",
    "S7": "#E04B4B",
}


def fig_5_11_tactic_bars() -> None:
    df = pd.DataFrame(TACTIC_COUNTS, columns=["tactic", "ckc", "count"])
    df = df.sort_values("count", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(9, 6))
    bars = ax.barh(
        df["tactic"],
        df["count"],
        color=[CKC_COLORS[c] for c in df["ckc"]],
        edgecolor="white",
        linewidth=0.6,
    )
    ax.set_xscale("log")
    ax.set_xlabel("Number of records (log scale)")
    ax.set_xlim(1, 50000)
    ax.grid(axis="x", which="both", linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)

    for bar, ckc, count in zip(bars, df["ckc"], df["count"]):
        ax.text(
            bar.get_width() * 1.15,
            bar.get_y() + bar.get_height() / 2,
            f"{count:,} ({ckc})",
            va="center",
            ha="left",
            fontsize=9,
        )

    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=CKC_COLORS[s])
        for s in sorted(CKC_COLORS.keys())
    ]
    ax.legend(
        legend_handles,
        sorted(CKC_COLORS.keys()),
        title="CKC stage",
        loc="lower right",
        frameon=False,
        ncol=6,
        bbox_to_anchor=(1.0, -0.18),
    )
    fig.tight_layout()
    out = OUT_DIR / "dataset_tactic_bars.pdf"
    fig.savefig(out, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=200)
    print(f"  wrote {out.name} (and .png)")
    plt.close(fig)


if __name__ == "__main__":
    print("Generating Chapter 5 dataset charts...")
    fig_5_10_class_split()
    fig_5_11_tactic_bars()
    print("Done.")
