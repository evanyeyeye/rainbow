"""
Generates the figures for the HRMS profile data-model page
(``docs/source/agilent/hrms_data_model.rst``).

Run with the docs virtualenv from the repo root::

    .venv-docs/bin/python docs/source/agilent/figures/make_figures.py

The SVGs are written next to this script and committed, so the documentation
build does not need to run matplotlib.
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
BLUE, ORANGE, RED = "#1f77b4", "#e08a00", "#d62728"


def _save(fig, name):
    fig.savefig(os.path.join(HERE, name), format="svg", bbox_inches="tight")
    plt.close(fig)


def data_rectangle():
    """ Intensities form a full rectangle, but the m/z labelling each column is
    not shared across scans. """
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    ncol, nrow = 5, 3
    mz_early = ["100.00", "100.02", "100.03", "100.05", r"$\cdots$"]
    mz_late = ["100.05", "100.07", "100.08", "100.10", r"$\cdots$"]

    # Two m/z header strips: the same columns are labelled differently per scan.
    for c in range(ncol):
        ax.text(c + 0.5, 2.05, mz_early[c], ha="center", va="center",
                fontsize=8, color=BLUE)
        ax.text(c + 0.5, 1.55, mz_late[c], ha="center", va="center",
                fontsize=8, color=ORANGE)
    ax.text(-0.15, 2.05, "m/z in scan 0:", ha="right", va="center",
            fontsize=8, color=BLUE)
    ax.text(-0.15, 1.55, "m/z in scan 1200:", ha="right", va="center",
            fontsize=8, color=ORANGE)
    ax.annotate("point index j", xy=(ncol, 2.5), xytext=(0, 2.5),
                ha="left", va="center", fontsize=9,
                arrowprops=dict(arrowstyle="->", color="0.3"))

    # The intensity rectangle (every row the same width: a full, non-ragged grid).
    for r in range(nrow):
        for c in range(ncol):
            ax.add_patch(Rectangle((c, -r), 1, 1, fill=False, edgecolor="0.5"))
            txt = r"$\cdots$" if c == ncol - 1 else f"$I_{{{r}{c}}}$"
            ax.text(c + 0.5, -r + 0.5, txt, ha="center", va="center",
                    fontsize=11)
        ax.text(ncol + 0.15, -r + 0.5, f"scan {r}", ha="left", va="center",
                fontsize=8, color="0.4")
    ax.text(-0.2, -nrow / 2.0 + 0.5, r"$\mathrm{data}[i][j] =$",
            ha="right", va="center", fontsize=12)

    ax.set_xlim(-2.0, ncol + 1.2)
    ax.set_ylim(-nrow + 0.0, 2.45)
    ax.set_aspect("equal")
    ax.axis("off")
    _save(fig, "data_rectangle.svg")


def mz_drift():
    """ The m/z the calibration assigns to one fixed flight time drifts,
    roughly linearly, over the run. """
    fig, ax = plt.subplots(figsize=(5.8, 3.0))
    scans = np.arange(0, 1256)
    drift = -0.024 * (scans / scans.max())          # shift from the start
    ax.plot(scans, drift, color=BLUE, lw=2)
    ax.axhline(0, color="0.75", lw=0.8)

    ax.annotate("", xy=(1255, drift[-1]), xytext=(1255, 0),
                arrowprops=dict(arrowstyle="<->", color=RED))
    ax.text(1235, drift[-1] / 2, "drift\n~0.024 Da",
            color=RED, ha="right", va="center", fontsize=9)
    # The gap between adjacent points in one scan, for comparison.
    ax.axhspan(-0.016, 0, xmin=0.02, xmax=0.10, color="0.85", zorder=0)
    ax.annotate("", xy=(45, -0.016), xytext=(45, 0),
                arrowprops=dict(arrowstyle="<->", color="0.4"))
    ax.text(85, -0.008, "gap between adjacent\npoints in one scan\n~0.016 Da",
            color="0.3", ha="left", va="center", fontsize=8)

    ax.set_xlabel("scan index i (time through the run)")
    ax.set_ylabel("change in assigned m/z (Da)")
    ax.set_title("the m/z assigned to one fixed flight time, vs. time "
                 "(starts at ~1556.36)", fontsize=9)
    ax.set_ylim(-0.030, 0.004)
    ax.set_xlim(-30, 1300)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "mz_drift.svg")


def shared_grid_zeros():
    """ Two scans sample at slightly different m/z (drift), so they occupy
    different bins. The shared axis is the union, and each scan reads 0 in the
    bins only the other scan filled. """
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(6.6, 3.8), sharex=True,
        gridspec_kw=dict(height_ratios=[1.0, 0.9], hspace=0.35))

    base = 100.0
    centers = np.round(base + 0.01 * np.arange(12), 2)        # 100.00 .. 100.11
    edges = np.round(np.append(centers - 0.005, centers[-1] + 0.005), 3)
    a = base + 0.004 + 0.016 * np.arange(7)                   # scan A positions
    b = a + 0.006                                            # scan B (drifted)
    bins_a = sorted(set(np.round((a - base) / 0.01).astype(int)))
    bins_b = sorted(set(np.round((b - base) / 0.01).astype(int)))
    union = sorted(set(bins_a) | set(bins_b))

    def draw_bins(ax):
        for k in range(len(centers)):
            if k % 2 == 0:
                ax.axvspan(edges[k], edges[k + 1], color="0.94", zorder=0)
        for e in edges:
            ax.axvline(e, color="0.82", lw=0.7, zorder=0)

    # Top: where each scan actually samples (different positions = drift).
    draw_bins(ax1)
    ax1.scatter(a, np.full_like(a, 1.0), s=26, color=BLUE, zorder=3)
    ax1.scatter(b, np.full_like(b, 0.5), s=26, color=ORANGE, zorder=3)
    ax1.text(edges[0] - 0.002, 1.0, "scan A", ha="right", va="center",
             fontsize=9, color=BLUE)
    ax1.text(edges[0] - 0.002, 0.5, "scan B", ha="right", va="center",
             fontsize=9, color=ORANGE)
    ax1.set_ylim(0.1, 1.4)
    ax1.set_yticks([])
    ax1.set_title("the two scans sample at slightly different m/z (drift)",
                  fontsize=9)

    # Bottom: the shared grid = union of occupied bins; 0 where only the other
    # scan landed.
    draw_bins(ax2)
    for row_y, occ, colour, label in (
            (1.0, bins_a, BLUE, "scan A"), (0.5, bins_b, ORANGE, "scan B")):
        for k in union:
            if k in occ:
                ax2.scatter([centers[k]], [row_y], s=30, color=colour, zorder=3)
            else:
                ax2.scatter([centers[k]], [row_y], s=34, facecolors="white",
                            edgecolors=RED, linewidths=1.4, zorder=3)
                ax2.annotate("0", (centers[k], row_y), color=RED, fontsize=8,
                             ha="center", va="center", zorder=4)
        ax2.text(edges[0] - 0.002, row_y, label, ha="right", va="center",
                 fontsize=9, color=colour)
    ax2.set_ylim(0.1, 1.4)
    ax2.set_yticks([])
    ax2.set_xlabel("shared m/z grid (bins, 0.01 Da)")
    ax2.set_title("each scan reads 0 (red) in the bins only the other scan "
                  "filled", fontsize=9)
    ax2.set_xticks(centers)
    ax2.set_xticklabels([f"{c:.2f}" for c in centers], fontsize=7, rotation=45)

    for ax in (ax1, ax2):
        ax.spines[["top", "right", "left"]].set_visible(False)
    _save(fig, "shared_grid_zeros.svg")


if __name__ == "__main__":
    data_rectangle()
    mz_drift()
    shared_grid_zeros()
    print("wrote:", ", ".join(sorted(
        f for f in os.listdir(HERE) if f.endswith(".svg"))))
