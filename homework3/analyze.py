# analyze.py
# HW3 — load results.csv, run one-way ANOVA per dimension, save boxplot
# Coinbase Spot Reporter — DSAI 5381

# Topic: tests whether the Agent 3 prompt choice (A / B / C) significantly
# changes each validation dimension. Uses scipy.stats.f_oneway and matplotlib.

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")  # headless-safe
    import matplotlib.pyplot as plt
    from scipy import stats
except ImportError as exc:  # noqa: BLE001
    sys.exit(
        "Missing dependency: install scipy and matplotlib first.\n"
        "  pip install scipy matplotlib\n"
        f"({exc})"
    )

_HW3_DIR = Path(__file__).resolve().parent
RESULTS_PATH = _HW3_DIR / "results.csv"
ANOVA_PATH = _HW3_DIR / "anova_results.txt"
BOXPLOT_PATH = _HW3_DIR / "boxplot.png"

DIMENSIONS = [
    "numeric_grounding",
    "disclaimer_compliance",
    "stakeholder_fit",
    "conciseness",
]


def main() -> None:
    if not RESULTS_PATH.exists():
        sys.exit(f"ERROR: {RESULTS_PATH} not found. Run run_experiment.py first.")

    df = pd.read_csv(RESULTS_PATH)
    if df.empty:
        sys.exit(f"ERROR: {RESULTS_PATH} has no rows yet.")

    print(f"Loaded {len(df)} rows from {RESULTS_PATH}")
    print("Counts per prompt:")
    print(df["prompt_label"].value_counts().to_string())
    print()

    # 1. ANOVA per dimension
    lines: list[str] = ["HW3 — One-way ANOVA per validation dimension", "=" * 56, ""]
    for dim in DIMENSIONS:
        if dim not in df.columns:
            continue

        groups = []
        labels = []
        for label, group in df.groupby("prompt_label"):
            vals = pd.to_numeric(group[dim], errors="coerce").dropna()
            if len(vals) >= 2:
                groups.append(vals.values)
                labels.append(label)

        if len(groups) < 2:
            lines.append(f"{dim}: not enough non-missing groups for ANOVA")
            continue

        f_stat, p_val = stats.f_oneway(*groups)
        means = {lab: float(g.mean()) for lab, g in zip(labels, groups)}
        sig = "REJECT H0 (p<0.05)" if p_val < 0.05 else "fail to reject H0"
        lines.append(f"-- {dim}")
        lines.append(f"   F = {f_stat:.4f}, p = {p_val:.4g}  -> {sig}")
        lines.append(f"   group means: {means}")
        lines.append("")

    text = "\n".join(lines)
    print(text)
    ANOVA_PATH.write_text(text + "\n", encoding="utf-8")
    print(f"Saved -> {ANOVA_PATH}")

    # 2. Boxplot — one subplot per dimension
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    axes = axes.flatten()
    plot_data = []
    plot_labels = sorted(df["prompt_label"].unique())

    for ax, dim in zip(axes, DIMENSIONS):
        if dim not in df.columns:
            ax.set_visible(False)
            continue
        data = []
        for label in plot_labels:
            vals = pd.to_numeric(df[df["prompt_label"] == label][dim], errors="coerce").dropna()
            data.append(vals.values)
        bp = ax.boxplot(data, tick_labels=plot_labels, patch_artist=True)
        for patch in bp["boxes"]:
            patch.set_facecolor("#5b8def")
            patch.set_alpha(0.7)
        ax.set_title(dim.replace("_", " "))
        ax.set_ylabel("score")
        ax.grid(True, axis="y", linestyle=":", alpha=0.4)

    fig.suptitle("HW3 — validation scores by prompt variant", fontsize=14)
    fig.tight_layout()
    fig.savefig(BOXPLOT_PATH, dpi=150)
    print(f"Saved -> {BOXPLOT_PATH}")


if __name__ == "__main__":
    main()
