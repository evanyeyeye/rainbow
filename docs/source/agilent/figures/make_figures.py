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
BLUE, RED = "#1f77b4", "#d62728"


def _save(fig, name):
    fig.savefig(os.path.join(HERE, name), format="svg", bbox_inches="tight")
    plt.close(fig)


def data_rectangle():
    """ The intensities form a clean (scans x points) rectangle. """
    fig, ax = plt.subplots(figsize=(5.0, 2.2))
    ncol, nrow = 5, 3
    for r in range(nrow):
        for c in range(ncol):
            ax.add_patch(Rectangle((c, -r), 1, 1, fill=False, edgecolor="0.5"))
            txt = r"$\cdots$" if c == ncol - 1 else f"$I_{{{r}{c}}}$"
            ax.text(c + 0.5, -r + 0.5, txt, ha="center", va="center",
                    fontsize=11)
    ax.annotate("point index j", xy=(ncol, 1.2), xytext=(0, 1.2),
                ha="left", va="center", fontsize=9,
                arrowprops=dict(arrowstyle="->", color="0.3"))
    ax.annotate("scan index i", xy=(-0.4, -nrow + 1), xytext=(-0.4, 1),
                ha="center", va="bottom", rotation=90, fontsize=9,
                arrowprops=dict(arrowstyle="->", color="0.3"))
    ax.text(ncol / 2, -nrow - 0.3,
            r"each cell is one intensity, $\mathrm{data}[i][j]$",
            ha="center", va="top", fontsize=9)
    ax.set_xlim(-1.0, ncol + 0.2)
    ax.set_ylim(-nrow - 0.8, 1.6)
    ax.set_aspect("equal")
    ax.axis("off")
    _save(fig, "data_rectangle.svg")


def mz_drift():
    """ The m/z assigned to a fixed point index drifts across the run, by more
    than the spacing between neighbouring points. Plotted as a change from the
    start, to avoid an unreadable axis offset. """
    fig, ax = plt.subplots(figsize=(5.8, 3.0))
    scans = np.arange(0, 1256)
    drift = -0.024 * (scans / scans.max())          # shift from the start
    ax.plot(scans, drift, color=BLUE, lw=2)
    ax.axhline(0, color="0.75", lw=0.8)

    # Right: total drift over the run.
    ax.annotate("", xy=(1255, drift[-1]), xytext=(1255, 0),
                arrowprops=dict(arrowstyle="<->", color=RED))
    ax.text(1235, drift[-1] / 2, "drift\n~0.024 Da",
            color=RED, ha="right", va="center", fontsize=9)
    # Left: the spacing to the neighbouring point, for comparison.
    ax.annotate("", xy=(45, -0.016), xytext=(45, 0),
                arrowprops=dict(arrowstyle="<->", color="0.4"))
    ax.text(80, -0.008, "spacing between\nneighbouring points\n~0.016 Da",
            color="0.3", ha="left", va="center", fontsize=8)

    ax.set_xlabel("scan number (time through the run)")
    ax.set_ylabel("m/z shift from the start (Da)")
    ax.set_title("one fixed point index (starts at m/z ~ 1556.36)", fontsize=9)
    ax.set_ylim(-0.030, 0.004)
    ax.set_xlim(-30, 1300)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "mz_drift.svg")


def shared_grid_zeros():
    """ Binning one scan's real points onto a uniform grid: each point rounds to
    its nearest bin, and bins that receive no point become inserted zeros. """
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(6.4, 4.2), sharex=True,
        gridspec_kw=dict(hspace=0.35))

    base = 800.0
    centers = np.round(base + 0.01 * np.arange(11), 2)      # 800.00 .. 800.10
    edges = np.round(np.append(centers - 0.005, centers[-1] + 0.005), 3)
    pts = base + 0.004 + 0.016 * np.arange(7)               # measured points
    inten = 45 + 55 * np.exp(-((pts - 800.05) / 0.06) ** 2)
    snap = np.round((pts - base) / 0.01).astype(int)        # nearest bin index
    filled = {int(s): inten[k] for k, s in enumerate(snap)}

    def draw_bins(ax):
        for k in range(len(centers)):
            if k % 2 == 0:
                ax.axvspan(edges[k], edges[k + 1], color="0.94", zorder=0)
        for e in edges:
            ax.axvline(e, color="0.8", lw=0.7, zorder=0)

    # Top: the real measured points, with an arrow showing the rounding.
    draw_bins(ax1)
    ax1.vlines(pts, 0, inten, color=BLUE, lw=1.6, zorder=3)
    ax1.scatter(pts, inten, s=28, color=BLUE, zorder=4)
    for k, p in enumerate(pts):
        c = centers[snap[k]]
        if abs(p - c) > 5e-4:
            ax1.annotate("", xy=(c, 7), xytext=(p, 7),
                         arrowprops=dict(arrowstyle="->", color="0.45", lw=1))
    ax1.set_ylim(0, 110)
    ax1.set_ylabel("intensity")
    ax1.set_title("measured points (~0.016 Da apart); arrows = rounding to the "
                  "nearest grid value", fontsize=9)

    # Bottom: the binned result. Filled bins get the intensity; empty bins -> 0.
    draw_bins(ax2)
    for k in range(len(centers)):
        if k in filled:
            ax2.bar(centers[k], filled[k], width=0.0075, color=BLUE, zorder=3)
        else:
            ax2.scatter([centers[k]], [0], s=40, facecolors="white",
                        edgecolors=RED, linewidths=1.5, zorder=4)
            ax2.annotate("0", (centers[k], 0), textcoords="offset points",
                         xytext=(0, 7), ha="center", color=RED, fontsize=9)
    ax2.set_ylim(0, 110)
    ax2.set_ylabel("intensity")
    ax2.set_title("after binning onto the 0.01 Da grid: empty bins become 0 "
                  "(red)", fontsize=9)
    ax2.set_xlabel("m/z (Da), labelled at bin centres")
    ax2.set_xticks(centers)
    ax2.set_xticklabels([f"{c:.2f}" for c in centers], fontsize=8, rotation=45)

    for ax in (ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "shared_grid_zeros.svg")


if __name__ == "__main__":
    data_rectangle()
    mz_drift()
    shared_grid_zeros()
    print("wrote:", ", ".join(sorted(
        f for f in os.listdir(HERE) if f.endswith(".svg"))))
