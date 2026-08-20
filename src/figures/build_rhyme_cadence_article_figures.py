#!/usr/bin/env python3
"""Build the three manuscript figures from frozen analysis outputs.

The script never recomputes the analysis.  It reads the compact, versioned
CSV/JSON outputs and writes each figure as PNG, TIFF, PDF, and SVG.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import PercentFormatter


BOOKS = ["genesis", "exodus", "leviticus", "numbers", "deuteronomy"]
BOOK_LABELS = {
    "genesis": "Genesis",
    "exodus": "Exodus",
    "leviticus": "Leviticus",
    "numbers": "Numbers",
    "deuteronomy": "Deuteronomy",
}
BLUE = "#286A8E"
ORANGE = "#C66B2E"
GRID = "#D9D9D9"
TEXT = "#202020"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-dir",
        type=Path,
        required=True,
        help="Directory of the v1.0.1 MAIN STRICT distribution run.",
    )
    parser.add_argument(
        "--exact-block-statistics",
        type=Path,
        required=True,
        help="ALL_block_distribution_statistics.csv from the exact-word-exclusion control.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=600)
    return parser.parse_args()


def set_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.0,
            "axes.titlesize": 10.0,
            "axes.labelsize": 9.0,
            "xtick.labelsize": 8.2,
            "ytick.labelsize": 8.2,
            "axes.edgecolor": TEXT,
            "axes.linewidth": 0.8,
            "text.color": TEXT,
            "axes.labelcolor": TEXT,
            "xtick.color": TEXT,
            "ytick.color": TEXT,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def save_all(fig: plt.Figure, out_dir: Path, stem: str, dpi: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    common = dict(bbox_inches="tight", facecolor="white")
    targets = {
        "pdf": out_dir / f"{stem}.pdf",
        "svg": out_dir / f"{stem}.svg",
        "png": out_dir / f"{stem}.png",
        "tiff": out_dir / f"{stem}.tiff",
    }
    # Write vector formats before the large raster exports. This avoids an
    # empty-PDF failure seen with one Matplotlib backend after TIFF rendering.
    fig.savefig(targets["pdf"], **common)
    fig.savefig(targets["svg"], **common)
    fig.savefig(targets["png"], dpi=dpi, **common)
    fig.savefig(
        targets["tiff"],
        dpi=dpi,
        pil_kwargs={"compression": "tiff_lzw"},
        **common,
    )
    for path in targets.values():
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Figure export failed: {path}")
    plt.close(fig)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_summary(main_dir: Path, book: str) -> dict:
    path = main_dir / f"{book}_summary.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("analysis_version") != "1.0.1":
        raise ValueError(f"Expected analysis_version 1.0.1 in {path}")
    if data.get("book") != book:
        raise ValueError(f"Book mismatch in {path}")
    return data


def read_block_metric(path: Path, metric: str) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for row in read_csv(path):
        if (
            row["scope"] == "ALL"
            and row["level"] in {"minor", "major"}
            and row["metric"] == metric
        ):
            result[row["level"]] = {
                "observed": float(row["observed"]),
                "null": float(row["null_mean"]),
            }
    if set(result) != {"minor", "major"}:
        raise ValueError(f"Missing {metric!r} rows in {path}")
    return result


def figure_1(main_dir: Path, out_dir: Path, dpi: int) -> None:
    values: dict[str, list[float]] = {"minor": [], "major": []}
    for book in BOOKS:
        alignment = read_summary(main_dir, book)["book_alignment"]
        for level in values:
            values[level].append(float(alignment[level]["summary"]["difference"]))

    y = np.arange(len(BOOKS))
    fig, ax = plt.subplots(figsize=(7.05, 3.45), layout="constrained")
    ax.axvline(0, color="#8A8A8A", linewidth=0.9, zorder=0)
    ax.hlines(y, values["major"], values["minor"], color="#BEBEBE", linewidth=1.4, zorder=1)
    ax.scatter(
        values["minor"], y, s=49, marker="o", facecolor="white", edgecolor=BLUE,
        linewidth=1.45, label="Minor boundary", zorder=3,
    )
    ax.scatter(
        values["major"], y, s=46, marker="s", facecolor=ORANGE, edgecolor="#4A2A1B",
        linewidth=0.8, label="Major boundary", zorder=3,
    )
    for level, dx in (("minor", 0.0012), ("major", -0.0012)):
        for x_value, yy in zip(values[level], y):
            ax.text(
                x_value + dx, yy, f"{x_value:.3f}", va="center",
                ha="left" if dx > 0 else "right", fontsize=7.8,
            )
    ax.set_yticks(y, [BOOK_LABELS[b] for b in BOOKS])
    ax.invert_yaxis()
    ax.set_xlim(0, 0.064)
    ax.set_xlabel("Observed − translation-null burst-end hit rate")
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2)
    save_all(fig, out_dir, "Figure1_book_alignment", dpi)


def figure_2(main_dir: Path, exact_path: Path, out_dir: Path, dpi: int) -> None:
    main_path = main_dir / "ALL_block_distribution_statistics.csv"
    full_share = read_block_metric(main_path, "positive_block_difference_share")
    exact_share = read_block_metric(exact_path, "positive_block_difference_share")
    full_median = read_block_metric(main_path, "median_block_hit_rate_difference")
    exact_median = read_block_metric(exact_path, "median_block_hit_rate_difference")

    levels = ["minor", "major"]
    labels = ["Minor", "Major"]
    x = np.arange(2)
    offset = 0.14
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.35))
    fig.subplots_adjust(left=0.10, right=0.99, top=0.84, bottom=0.27, wspace=0.43)

    ax = axes[0]
    for i, level in enumerate(levels):
        ax.plot(
            [x[i] - offset, x[i] + offset],
            [full_share[level]["observed"], exact_share[level]["observed"]],
            color="#BEBEBE", linewidth=1.3, zorder=1,
        )
    ax.scatter(
        x - offset, [full_share[l]["observed"] for l in levels], s=50, marker="o",
        facecolor="white", edgecolor=BLUE, linewidth=1.45, label="All accepted links", zorder=3,
    )
    ax.scatter(
        x + offset, [exact_share[l]["observed"] for l in levels], s=48, marker="s",
        facecolor=ORANGE, edgecolor="#4A2A1B", linewidth=0.8,
        label="Exact-word links excluded", zorder=3,
    )
    null_share = np.mean(
        [full_share[l]["null"] for l in levels] + [exact_share[l]["null"] for l in levels]
    )
    ax.axhline(
        null_share, color="#737373", linestyle=(0, (3, 2)), linewidth=0.9,
        label="Permutation-null mean",
    )
    ax.set_xticks(x, labels)
    ax.set_ylim(0.42, 0.88)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_ylabel("Blocks with positive difference")
    ax.set_title("A. Direction across fixed blocks", loc="left", fontweight="bold")

    ax = axes[1]
    for i, level in enumerate(levels):
        ax.plot(
            [x[i] - offset, x[i] + offset],
            [full_median[level]["observed"], exact_median[level]["observed"]],
            color="#BEBEBE", linewidth=1.3, zorder=1,
        )
    ax.scatter(
        x - offset, [full_median[l]["observed"] for l in levels], s=50, marker="o",
        facecolor="white", edgecolor=BLUE, linewidth=1.45, zorder=3,
    )
    ax.scatter(
        x + offset, [exact_median[l]["observed"] for l in levels], s=48, marker="s",
        facecolor=ORANGE, edgecolor="#4A2A1B", linewidth=0.8, zorder=3,
    )
    ax.axhline(0, color="#737373", linestyle=(0, (3, 2)), linewidth=0.9)
    ax.set_xticks(x, labels)
    ax.set_ylim(-0.004, 0.044)
    ax.set_ylabel("Median hit-rate difference")
    ax.set_title("B. Median block effect", loc="left", fontweight="bold")

    for ax in axes:
        ax.grid(axis="y", color=GRID, linewidth=0.7)
        ax.spines[["top", "right"]].set_visible(False)

    handles, labels_legend = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels_legend, frameon=False, loc="lower center", ncol=3,
        bbox_to_anchor=(0.5, 0.015), handletextpad=0.5, columnspacing=1.15,
    )
    save_all(fig, out_dir, "Figure2_block_robustness", dpi)


def figure_3(main_dir: Path, out_dir: Path, dpi: int) -> None:
    rows = read_csv(main_dir / "ALL_verse_coverage.csv")
    grouped: dict[str, list[dict[str, str]]] = {book: [] for book in BOOKS}
    for row in rows:
        if row["book"] not in grouped:
            raise ValueError(f"Unexpected book {row['book']!r}")
        grouped[row["book"]].append(row)

    coverage: dict[str, tuple[float, float]] = {}
    activity: dict[str, np.ndarray] = {}
    for book in BOOKS:
        book_rows = sorted(grouped[book], key=lambda r: int(r["canonical_verse_ordinal"]))
        values = np.full(len(book_rows), np.nan)
        full_rows = []
        for i, row in enumerate(book_rows):
            if int(row["fully_represented_after_left_window"]) != 1:
                continue
            full_rows.append(row)
            eligible = int(row["eligible_positions"])
            active = int(row["active_positions"])
            values[i] = active / eligible if eligible else np.nan
        activity[book] = values
        coverage[book] = (
            np.mean([int(r["has_rhyme_activity"]) for r in full_rows]),
            np.mean([int(r["has_burst_end"]) for r in full_rows]),
        )

    fig = plt.figure(figsize=(7.4, 3.9))
    gs = fig.add_gridspec(1, 2, width_ratios=(3.7, 1.75))
    fig.subplots_adjust(left=0.10, right=0.99, top=0.86, bottom=0.25, wspace=0.35)
    ax_heat = fig.add_subplot(gs[0, 0])
    ax_cov = fig.add_subplot(gs[0, 1])

    colors = ["#F7FBFF", "#C6DBEF", "#6BAED6", "#2171B5", "#08306B"]
    cmap = LinearSegmentedColormap.from_list("verse_activity", colors)
    cmap.set_bad("#D8D8D8")
    for row_index, book in enumerate(BOOKS):
        values = np.ma.masked_invalid(activity[book])[None, :]
        y = len(BOOKS) - 1 - row_index
        ax_heat.imshow(
            values,
            aspect="auto",
            interpolation="nearest",
            cmap=cmap,
            vmin=0,
            vmax=0.75,
            extent=(0, 100, y - 0.30, y + 0.30),
            rasterized=True,
        )
    ax_heat.set_yticks(
        np.arange(len(BOOKS))[::-1], [BOOK_LABELS[b] for b in BOOKS]
    )
    ax_heat.set_xlim(0, 100)
    ax_heat.set_ylim(-0.65, len(BOOKS) - 0.35)
    ax_heat.set_xticks([0, 25, 50, 75, 100])
    ax_heat.set_xlabel("Relative position within book (%)")
    ax_heat.set_title("A. Verse-level recurrence intensity", loc="left", fontweight="bold")
    ax_heat.tick_params(axis="y", length=0)
    ax_heat.spines[["top", "right", "left"]].set_visible(False)
    ax_heat.grid(axis="x", color="#ECECEC", linewidth=0.6, zorder=0)
    scalar = mpl.cm.ScalarMappable(norm=mpl.colors.Normalize(0, 0.75), cmap=cmap)
    cax = ax_heat.inset_axes([0.06, -0.23, 0.88, 0.07])
    cbar = fig.colorbar(
        scalar, cax=cax, orientation="horizontal", ticks=[0, 0.25, 0.50, 0.75]
    )
    cbar.set_label("Active eligible positions within verse")
    cbar.ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    cbar.outline.set_linewidth(0.6)

    y = np.arange(len(BOOKS))
    active_cov = np.array([coverage[b][0] for b in BOOKS]) * 100
    burst_cov = np.array([coverage[b][1] for b in BOOKS]) * 100
    ax_cov.hlines(y, burst_cov, active_cov, color="#BEBEBE", linewidth=1.25, zorder=1)
    ax_cov.scatter(
        active_cov, y, s=45, marker="o", facecolor="white", edgecolor=BLUE,
        linewidth=1.4, label="Any recurrence activity", zorder=3,
    )
    ax_cov.scatter(
        burst_cov, y, s=43, marker="s", facecolor=ORANGE, edgecolor="#4A2A1B",
        linewidth=0.8, label="At least one burst end", zorder=3,
    )
    for xx, yy in zip(active_cov, y):
        ax_cov.text(xx + 0.055, yy - 0.11, f"{xx:.1f}", fontsize=7.2, ha="left", va="center")
    for xx, yy in zip(burst_cov, y):
        ax_cov.text(xx - 0.055, yy + 0.13, f"{xx:.1f}", fontsize=7.2, ha="right", va="center")
    ax_cov.set_yticks(y, [])
    ax_cov.invert_yaxis()
    ax_cov.set_xlim(96.5, 99.0)
    ax_cov.set_xticks([97, 98, 99])
    ax_cov.set_xlabel("Fully represented verses (%)")
    ax_cov.set_title("B. Coverage (expanded scale)", loc="left", fontweight="bold")
    ax_cov.grid(axis="x", color=GRID, linewidth=0.7)
    ax_cov.spines[["top", "right", "left"]].set_visible(False)
    ax_cov.tick_params(axis="y", length=0)
    ax_cov.legend(
        frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1,
        handletextpad=0.5, borderaxespad=0,
    )
    save_all(fig, out_dir, "Figure3_verse_coverage", dpi)


def main() -> None:
    args = parse_args()
    set_style()
    figure_1(args.main_dir, args.out_dir, args.dpi)
    figure_2(args.main_dir, args.exact_block_statistics, args.out_dir, args.dpi)
    figure_3(args.main_dir, args.out_dir, args.dpi)
    print(f"WROTE: {args.out_dir}")


if __name__ == "__main__":
    main()
