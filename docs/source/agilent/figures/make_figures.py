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
BLUE, RED, GREY = "#1f77b4", "#d62728", "#999999"


def _save(fig, name):
    fig.savefig(os.path.join(HERE, name), format="svg", bbox_inches="tight")
    plt.close(fig)


def data_rectangle():
    """ The intensities form a clean (scans x points) rectangle. """
    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    ncol, nrow = 5, 3
    for r in range(nrow):
        for c in range(ncol):
            ax.add_patch(Rectangle((c, -r), 1, 1, fill=False, edgecolor="0.5"))
            txt = r"$\cdots$" if c == ncol - 1 else f"$I_{{{r}{c}}}$"
            ax.text(c + 0.5, -r + 0.5, txt, ha="center", va="center",
                    fontsize=12)
    # j increases to the right, i increases downward.
    ax.annotate("point index j", xy=(ncol, 1.25), xytext=(0, 1.25),
                ha="left", va="center", fontsize=10,
                arrowprops=dict(arrowstyle="->", color="0.3"))
    ax.annotate("scan index i", xy=(-0.45, -nrow + 1), xytext=(-0.45, 1),
                ha="center", va="bottom", rotation=90, fontsize=10,
                arrowprops=dict(arrowstyle="->", color="0.3"))
    ax.text(ncol / 2, -nrow - 0.35,
            r"each cell is one intensity, $\mathrm{data}[i][j]$",
            ha="center", va="top", fontsize=10)
    ax.set_xlim(-1.1, ncol + 0.2)
    ax.set_ylim(-nrow - 0.9, 1.7)
    ax.set_aspect("equal")
    ax.axis("off")
    _save(fig, "data_rectangle.svg")


def mz_drift():
    """ The m/z of a fixed point index drifts across the run, by more than the
    spacing between neighbouring points. """
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    scans = np.arange(0, 1256)
    # A fixed point index: same flight time every scan, m/z drifts ~0.024 Da.
    mz0 = 1556.359
    mz = mz0 - 0.024 * (scans / scans.max())
    ax.plot(scans, mz, color=BLUE, lw=2,
            label="m/z of one fixed point index")
    # Shade a band one point-spacing tall, to compare drift against spacing.
    spacing = 0.016
    ax.axhspan(mz[-1], mz[-1] + spacing, color=GREY, alpha=0.30,
               label="spacing to the neighbouring point (~0.016 Da)")
    ax.annotate("", xy=(1255, mz[-1]), xytext=(1255, mz[0]),
                arrowprops=dict(arrowstyle="<->", color=RED))
    ax.text(1180, (mz[0] + mz[-1]) / 2, "drift\n~0.024 Da",
            color=RED, ha="right", va="center", fontsize=10)
    ax.set_xlabel("scan number (time through the run)")
    ax.set_ylabel("m/z (Da)")
    ax.legend(loc="lower left", fontsize=9, framealpha=0.9)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "mz_drift.svg")


def shared_grid_zeros():
    """ Forcing one scan's real points onto a uniform grid leaves empty grid
    columns, which become inserted zeros. """
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    lo, hi = 800.00, 800.105
    grid = np.round(np.arange(lo, hi, 0.01), 2)        # uniform 0.01 Da grid
    pts = np.arange(lo + 0.004, hi, 0.016)             # real points, ~0.016 apart
    inten = 40 + 60 * np.exp(-((pts - 800.052) / 0.035) ** 2)

    # Each real point rounds to its nearest grid column; the rest stay empty.
    hit = np.unique(np.round((pts - grid[0]) / 0.01).astype(int))
    empty = np.array([c for c in range(len(grid)) if c not in hit])

    for g in grid:                                     # the uniform grid
        ax.axvline(g, color="0.88", lw=1, zorder=0)
    ax.vlines(pts, 0, inten, color=BLUE, lw=1.6, zorder=2)
    ax.scatter(pts, inten, s=34, color=BLUE, zorder=3,
               label="actual measured points (~0.016 Da apart)")
    ax.scatter(grid[empty], np.zeros(len(empty)), s=42, facecolors="white",
               edgecolors=RED, linewidths=1.6, zorder=3,
               label="grid columns with no point  ->  inserted 0")

    ax.set_xlabel("m/z (Da)")
    ax.set_ylabel("intensity")
    ax.set_ylim(-12, 116)
    ax.set_xlim(lo - 0.004, hi - 0.004)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.95)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "shared_grid_zeros.svg")


if __name__ == "__main__":
    data_rectangle()
    mz_drift()
    shared_grid_zeros()
    print("wrote:", ", ".join(sorted(
        f for f in os.listdir(HERE) if f.endswith(".svg"))))
