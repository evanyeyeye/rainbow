"""
Generates the figures for the HRMS profile data-model page
(``docs/source/agilent/hrms_data_model.rst``).

Run with the docs virtualenv from the repo root::

    .venv-docs/bin/python docs/source/agilent/figures/make_figures.py

The SVGs are written next to this script and committed, so the documentation
build does not need to run matplotlib. Most figures are self-contained; the
worked-example heatmap reads the real ``tests/inputs/amber.D`` fixture (run-length
encoded, so no python-lzf is needed).
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
BLUE, ORANGE, RED, GREEN = "#1f77b4", "#e08a00", "#d62728", "#2ca02c"


def _save(fig, name, tight=True):
    # bbox_inches="tight" trims margins for the schematic figures; figures that
    # manage their own layout (constrained_layout, with a colorbar) pass
    # tight=False so the reserved colorbar space is not clipped.
    fig.savefig(os.path.join(HERE, name), format="svg",
                bbox_inches="tight" if tight else None)
    plt.close(fig)


def data_rectangle():
    """ Contrast the normal rainbow data model (the matrix columns ARE one shared
    m/z axis, ylabels) with the HRMS profile (columns are a shared flight time
    tof[j]; the m/z is per-scan mass_labels(i), so there is no single ylabels). """
    fig, (axn, axh) = plt.subplots(
        2, 1, figsize=(8.8, 6.9), gridspec_kw=dict(height_ratios=[1.0, 1.7]))
    ncol, nrow = 5, 3
    dx = 1.8
    mz_early = ["100.00", "100.02", "100.03", "100.05", r"$\cdots$"]
    mz_late = ["100.05", "100.07", "100.08", "100.10", r"$\cdots$"]
    tof_hdr = [r"$t_0$", r"$t_1$", r"$t_2$", r"$t_3$", r"$\cdots$"]
    xlim = (-5.2, dx * ncol + 4.3)

    def draw_cells(ax, row_colors, scan_labels):
        # Each data row is tinted its own colour so it maps to the same-colour
        # m/z header; the middle row is an ellipsis (many scans between).
        for r in range(nrow):
            for c in range(ncol):
                col = row_colors[r]
                ax.add_patch(Rectangle(
                    (dx * c, -r), dx, 1, fill=col is not None,
                    facecolor=col if col else "white",
                    alpha=0.28 if col else 1.0, edgecolor="0.5"))
                if r == 1:                       # middle: many scans omitted
                    ax.text(dx * (c + 0.5), -r + 0.5, r"$\vdots$", ha="center",
                            va="center", fontsize=11, color="0.5")
                elif c == ncol - 1:              # last column: more points
                    ax.text(dx * (c + 0.5), -r + 0.5, r"$\cdots$", ha="center",
                            va="center", fontsize=10, color="0.4")
            ax.text(dx * ncol + 0.25, -r + 0.5, scan_labels[r], ha="left",
                    va="center", fontsize=8,
                    color=row_colors[r] if row_colors[r] else "0.4")
        ax.text(-0.35, -(nrow - 1) / 2.0 + 0.5, r"$\mathrm{data}[i][j] =$",
                ha="right", va="center", fontsize=12)

    # --- Top: a normal rainbow file. One shared m/z axis = per-array mass
    # labels (ylabels). The same header is repeated above AND below the matrix
    # to stress that every row maps to it. ---
    for c in range(ncol):
        axn.text(dx * (c + 0.5), 1.12, mz_early[c], ha="center", va="bottom",
                 fontsize=8.5, color=GREEN)
        axn.text(dx * (c + 0.5), -2.18, mz_early[c], ha="center", va="top",
                 fontsize=8.5, color=GREEN)
    axn.text(-0.2, 1.12, "m/z = PER-ARRAY mass labels (ylabels):", ha="right",
             va="bottom", fontsize=9.5, color=GREEN, fontweight="bold")
    axn.text(-0.2, -2.18, "m/z = PER-ARRAY mass labels (ylabels):", ha="right",
             va="top", fontsize=9.5, color=GREEN, fontweight="bold")
    draw_cells(axn, [GREEN, None, GREEN], ["scan 0", r"$\vdots$", "scan N"])
    axn.set_title("(a) A normal rainbow file: one shared m/z axis "
                  "(per-array mass labels, ylabels)", fontsize=10, color="0.3")
    axn.set_xlim(*xlim)
    axn.set_ylim(-nrow - 0.55, 1.7)
    axn.axis("off")

    # --- Bottom: an HRMS profile. Columns are flight times; m/z is per scan.
    # The blue header (scan 0) sits above the top row; the orange header
    # (scan 1200) sits below the bottom row, mirroring panel (a). ---
    axh.annotate("point index j = flight time within a scan",
                 xy=(dx * ncol, 2.5), xytext=(0, 2.5), ha="left", va="center",
                 fontsize=9, arrowprops=dict(arrowstyle="->", color="0.3"))
    for c in range(ncol):
        axh.text(dx * (c + 0.5), 1.78, tof_hdr[c], ha="center", va="bottom",
                 fontsize=9.5, color="0.25")
        axh.text(dx * (c + 0.5), 1.10, mz_early[c], ha="center", va="bottom",
                 fontsize=8.5, color=BLUE)
        axh.text(dx * (c + 0.5), -2.18, mz_late[c], ha="center", va="top",
                 fontsize=8.5, color=ORANGE)
    axh.text(-0.2, 1.78, "flight time tof[j] (shared):", ha="right",
             va="bottom", fontsize=8.5, color="0.25")
    axh.text(-0.2, 1.10, "m/z = PER-SCAN mass_labels(0):", ha="right",
             va="bottom", fontsize=9.5, color=BLUE, fontweight="bold")
    axh.text(-0.2, -2.18, "m/z = PER-SCAN mass_labels(1200):", ha="right",
             va="top", fontsize=9.5, color=ORANGE, fontweight="bold")
    draw_cells(axh, [BLUE, None, ORANGE], ["scan 0", r"$\vdots$", "scan 1200"])
    x_rt = dx * ncol + 2.4
    axh.annotate("", xy=(x_rt, -nrow + 1.05), xytext=(x_rt, 0.95),
                 arrowprops=dict(arrowstyle="->", color="0.4"))
    axh.text(x_rt + 0.18, -(nrow - 1) / 2.0 + 0.5, "retention\ntime i",
             ha="left", va="center", fontsize=8, color="0.4")
    y_k = -nrow + 0.0
    axh.annotate("", xy=(0, y_k), xytext=(dx * ncol, y_k),
                 arrowprops=dict(arrowstyle="<->", color="0.45"))
    axh.text(dx * ncol / 2.0, y_k - 0.30, "k points per scan (one row)",
             ha="center", va="top", fontsize=8.5, color="0.35")
    axh.set_title("(b) An HRMS profile: per-scan mass labels mass_labels(i), "
                  "no shared ylabels", fontsize=10, color="0.3")
    axh.set_xlim(*xlim)
    axh.set_ylim(-nrow - 0.95, 2.85)
    axh.axis("off")
    _save(fig, "data_rectangle.svg")


def mz_drift():
    """ Draw the actual m/z sample positions of a few scans as combs of ticks.
    Every scan samples at the same even spacing, but drift slides the whole comb,
    so different scans sample different m/z and no single m/z is shared by all. """
    fig, ax = plt.subplots(figsize=(7.4, 3.8))

    d = 0.016                                  # spacing within one scan (Da)
    base = np.round(np.arange(100.0, 100.178, d), 3)   # scan 0's positions
    # Early, middle, late scan; drift slides the comb left over the run. Lanes are
    # spaced 1.6 apart (not 1.0) so the dt arrows clear the comb above them.
    lanes = [("scan 0", 0.000, 0.0, BLUE),
             ("scan 628", -0.012, -1.6, GREEN),
             ("scan 1255", -0.024, -3.2, ORANGE)]
    xlo, xhi = 100.0, 100.162

    lane_pts = {}
    for name, off, y, color in lanes:
        # Clip to a common window so every comb spans the full width and the
        # scan labels have clear space to their left.
        pts = base + off
        pts = pts[(pts >= xlo - 1e-9) & (pts <= xhi)]
        lane_pts[y] = pts
        ax.vlines(pts, y - 0.28, y + 0.28, color=color, lw=1.7)
        ax.text(99.972, y, name, ha="left", va="center", fontsize=9,
                color=color)

    # Reference lines at scan 0's positions. Scan 0's ticks sit on them; scan
    # 628's and scan 1255's fall progressively to the LEFT, so a viewer can see
    # at a glance that the combs do not line up - they drift.
    for x in base[(base >= xlo) & (base <= xhi)]:
        ax.plot([x, x], [-3.54, 0.34], color="0.72", lw=0.9, zorder=0)

    # Ions are summed over fixed flight-time intervals: the step between
    # consecutive ticks is a constant clock interval dt, the SAME in every scan.
    # Double-headed arrows mark dt: three steps on scan 0 (first four ticks) and
    # one step on each later scan, so the eye can check the spacing is uniform
    # even as drift slides where those steps land in m/z.
    def dt_arrow(x0, x1, y, label=True):
        ya = y + 0.46
        ax.annotate("", xy=(x1, ya), xytext=(x0, ya),
                    arrowprops=dict(arrowstyle="<->", color="0.4", lw=1.0))
        if label:
            ax.text((x0 + x1) / 2.0, ya + 0.02, r"$\Delta t$", ha="center",
                    va="bottom", fontsize=8, color="0.4")

    for k in range(3):                              # scan 0: first four ticks
        p = lane_pts[0]
        dt_arrow(p[k], p[k + 1], 0, label=(k == 0))
    for y in (-1.6, -3.2):                          # later scans: first two ticks
        p = lane_pts[y]
        dt_arrow(p[0], p[1], y)

    # Track ONE measurement (index j) down the scans: same index, drifting m/z.
    jx = [round(base[5] + off, 3) for _, off, _, _ in lanes]  # .080 .068 .056
    jy = [0.0, -1.6, -3.2]
    ax.plot(jx, jy, color=RED, lw=1.6, zorder=5)
    ax.scatter(jx, jy, s=24, color=RED, zorder=6)
    ax.annotate("", xy=(jx[2], jy[2]), xytext=(jx[1], jy[1]),
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.6))

    ax.set_xlabel("m/z (Da)")
    ax.set_yticks([])
    ax.set_ylim(-3.7, 0.75)                         # just above the Delta-t labels
    ax.set_xlim(99.95, 100.175)
    ax.spines[["top", "right", "left"]].set_visible(False)
    _save(fig, "mz_drift.svg")


def shared_grid_zeros():
    """ Scan A and scan B drift into different 0.01 Da bins (shown one per
    panel), then stack into a single matrix where every empty bin reads 0. The
    matrix panel deliberately mirrors the data_rectangle figure. """
    fig = plt.figure(figsize=(7.4, 6.4))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 1.0, 1.5], hspace=0.55)
    ax_a = fig.add_subplot(gs[0])
    ax_b = fig.add_subplot(gs[1], sharex=ax_a, sharey=ax_a)
    ax_m = fig.add_subplot(gs[2], sharex=ax_a)

    base = 100.0
    nbin = 8
    centers = np.round(base + 0.01 * np.arange(nbin), 2)      # 100.00 .. 100.07
    edges = np.round(np.append(centers - 0.005, centers[-1] + 0.005), 3)

    # Scan A and scan B both sample at roughly even spacing, but drift has
    # shifted B so the two share some bins (0, 3, 7) and differ in the rest. Bin
    # 5 is sampled by NEITHER scan (the points straddle it), so it is empty in
    # every scan and gets dropped from the grid. The bins are chosen irregular on
    # purpose: a clean every-other-bin alternation would be a checkerboard
    # artifact, not what real drifting data looks like.
    bins_a = np.array([0, 2, 3, 6, 7])
    bins_b = np.array([0, 1, 3, 4, 7])
    a, b = centers[bins_a], centers[bins_b]

    def envelope(mz):
        return 35 + 75 * np.exp(-((mz - 0.035 - base) / 0.03) ** 2)
    int_a, int_b = envelope(a), envelope(b)

    def draw_bins(ax):
        for k in range(nbin):
            ax.axvspan(edges[k], edges[k + 1], color="0.95", zorder=0)
        for e in edges:
            ax.axvline(e, color="0.82", lw=0.7, zorder=0)

    # --- Panel 1: scan A on its own ---
    draw_bins(ax_a)
    ax_a.vlines(a, 0, int_a, color=BLUE, lw=1.8, zorder=3)
    ax_a.scatter(a, int_a, s=26, color=BLUE, zorder=4)
    ax_a.annotate("", xy=(edges[2], 122), xytext=(edges[3], 122),
                  arrowprops=dict(arrowstyle="<->", color="0.35", lw=1.0))
    ax_a.text(centers[2], 128, "one bin = 0.01 Da (100.015 to 100.025)",
              ha="center", va="bottom", fontsize=7.5, color="0.3")
    ax_a.set_ylim(0, 150)
    ax_a.set_ylabel("intensity", fontsize=8)
    ax_a.set_title("(a) scan A samples these bins", fontsize=9.5, color=BLUE)

    # --- Panel 2: scan B, drifted so it shares some bins and lands in new ones.
    draw_bins(ax_b)
    ax_b.vlines(b, 0, int_b, color=ORANGE, lw=1.8, zorder=3)
    ax_b.scatter(b, int_b, s=26, color=ORANGE, zorder=4)
    ax_b.set_title("(b) scan B has drifted: some bins shared with A, some new",
                   fontsize=9.5, color=ORANGE)
    ax_b.set_ylabel("intensity", fontsize=8)

    for ax in (ax_a, ax_b):
        ax.set_yticks([])
        ax.spines[["top", "right", "left"]].set_visible(False)
        plt.setp(ax.get_xticklabels(), visible=False)

    # --- Panel 3: stack the two scans into one matrix on the union of bins.
    # Drawn in the SAME m/z coordinates as the panels above (shared x-axis), so
    # each boxed cell sits directly under the stem it came from and the matrix is
    # exactly as wide; the boxed-cell style mirrors the data_rectangle figure.
    set_a, set_b = set(bins_a.tolist()), set(bins_b.tolist())
    union = set_a | set_b
    for k in range(nbin):
        if k not in union:
            # Empty in every scan: this bin is dropped, it never becomes a column
            # (so no surviving column is all zeros).
            ax_m.add_patch(Rectangle(
                (edges[k], -1), edges[k + 1] - edges[k], 2, facecolor="0.92",
                edgecolor="0.7", hatch="////", zorder=1))
            ax_m.annotate("dropped", xy=(centers[k], -1),
                          xytext=(centers[k], -1.65), ha="center", va="top",
                          fontsize=7.5, color="0.45",
                          arrowprops=dict(arrowstyle="->", color="0.55"))
            continue
        for r, (color, filled) in enumerate([(BLUE, set_a), (ORANGE, set_b)]):
            y = -r                               # row A at [0,1], row B at [-1,0]
            has = k in filled
            ax_m.add_patch(Rectangle(
                (edges[k], y), edges[k + 1] - edges[k], 1, fill=has,
                facecolor=color, alpha=0.40 if has else 1.0, edgecolor="0.5"))
            if not has:
                ax_m.text(centers[k], y + 0.5, "0", color=RED, ha="center",
                          va="center", fontsize=12, weight="bold")
    ax_m.axhline(0, color="0.5", lw=0.8)
    ax_m.set_ylim(-2.4, 1.15)
    ax_m.set_yticks([0.5, -0.5])
    ax_m.set_yticklabels(["scan A", "scan B"], fontsize=9.5)
    for tick, col in zip(ax_m.get_yticklabels(), (BLUE, ORANGE)):
        tick.set_color(col)
    ax_m.tick_params(left=False)
    ax_m.set_xlim(edges[0] - 0.002, edges[-1] + 0.002)
    ax_m.set_xticks(centers)
    ax_m.set_xticklabels([f"{c:.2f}" for c in centers], fontsize=7.5)
    ax_m.set_xlabel("shared m/z grid (each column is one 0.01 Da bin)",
                    fontsize=8)
    ax_m.set_title("(c) stacked onto the union of bins: shared bins fill both "
                   "rows, drifted bins read 0, empty bins are dropped",
                   fontsize=8.6)
    ax_m.spines[["top", "right", "left"]].set_visible(False)
    _save(fig, "shared_grid_zeros.svg")


# Real profile points from cyan.D, scan 0, across the m/z 825.42 peak (13
# consecutive points: the apex with a shoulder on each side, so it reads as a
# real peak). The centroid is the intensity-weighted center, 825.4236.
# Embedded so the figure builds with no fixtures at doc-build time.
_CYAN_PEAK_MZ = [825.3229, 825.3394, 825.3559, 825.3725, 825.3890, 825.4055,
                 825.4221, 825.4386, 825.4551, 825.4717, 825.4882, 825.5048,
                 825.5213]
_CYAN_PEAK_I = [859598, 744083, 691729, 747286, 916628, 1100528, 1177581,
                1122594, 997141, 861641, 753954, 708937, 766233]
_CYAN_CENTROID_MZ, _CYAN_CENTROID_I = 825.4236, 1177581


def centroid_vs_profile():
    """ One real Q-TOF peak (cyan.D scan 0) two ways: the profile keeps every
    sampled point of the curve; the centroid keeps one (m/z, intensity). """
    mz = np.array(_CYAN_PEAK_MZ)
    inten = np.array(_CYAN_PEAK_I) / 1e6           # millions, for tidy axis
    fig, (axp, axc) = plt.subplots(1, 2, figsize=(7.8, 3.1), sharey=True)

    # Profile: every sampled point of the curve.
    axp.fill_between(mz, 0, inten, color=BLUE, alpha=0.15, zorder=1)
    axp.plot(mz, inten, color=BLUE, lw=1.3, zorder=2)
    axp.scatter(mz, inten, s=22, color=BLUE, zorder=3)
    axp.set_title("(a) Profile", fontsize=11, color=BLUE)
    axp.text(0.5, 1.0, "every sampled point of the curve",
             transform=axp.transAxes, ha="center", va="top", fontsize=8,
             color="0.35")

    # Centroid: one (m/z, intensity) for the peak.
    axc.vlines(_CYAN_CENTROID_MZ, 0, _CYAN_CENTROID_I / 1e6, color=ORANGE,
               lw=2.4, zorder=3)
    axc.scatter([_CYAN_CENTROID_MZ], [_CYAN_CENTROID_I / 1e6], s=40,
                color=ORANGE, zorder=4)
    axc.set_title("(b) Centroid", fontsize=11, color=ORANGE)
    axc.text(0.5, 1.0, f"one (m/z, intensity): {_CYAN_CENTROID_MZ}",
             transform=axc.transAxes, ha="center", va="top", fontsize=8,
             color="0.35")

    for ax in (axp, axc):
        ax.set_xlabel("m/z (Da)", fontsize=9)
        ax.set_xlim(mz.min() - 0.01, mz.max() + 0.01)
        ax.set_ylim(0, 1.27)
        ax.set_yticks([])
        ax.spines[["top", "right", "left"]].set_visible(False)
    axp.set_ylabel("intensity", fontsize=9)
    _save(fig, "centroid_vs_profile.svg")


def centroid_zeros():
    """ Why a profile's binned matrix dwarfs a centroid's, for the SAME two peaks.
    Every measured point becomes a 3-column staircase (one fine bin per scan, the
    other two 0); empty bins between points are dropped (//). A profile peak is
    MANY points, so each peak is a row of staircases; a centroid peak is ONE
    point, so each peak is a single staircase. Both are 2/3 zeros, but the
    centroid matrix is far narrower. """
    fig, (axp, axc) = plt.subplots(2, 1, figsize=(9.2, 4.7),
                                   gridspec_kw=dict(height_ratios=[1, 1]))
    gap = 1.0          # dropped empty bins between adjacent points (within a peak)
    peakgap = 3.2      # many dropped empty bins between different peaks

    def staircase(ax, x0):
        for r in range(3):
            for c in range(3):
                hit = (c == r)
                ax.add_patch(Rectangle((x0 + c, -r), 1, 1, fill=hit,
                                       facecolor=BLUE, alpha=0.4 if hit else 1.0,
                                       edgecolor="0.6"))
                if not hit:
                    ax.text(x0 + c + 0.5, -r + 0.5, "0", color=RED, ha="center",
                            va="center", fontsize=8, weight="bold")

    def draw_peak(ax, x0, n):
        # A peak = n staircases (one per measured point), // between each.
        x = x0
        for k in range(n):
            staircase(ax, x)
            x += 3
            if k < n - 1:
                ax.text(x + gap / 2.0, -1.5, "//", ha="center", va="center",
                        fontsize=10, color="0.6")
                x += gap
        return x

    def peak_label(ax, xa, xb, name):
        ax.annotate("", xy=(xa, 1.25), xytext=(xb, 1.25),
                    arrowprops=dict(arrowstyle="-", color="0.55", lw=1.0))
        ax.text((xa + xb) / 2.0, 1.4, name, ha="center", va="bottom",
                fontsize=8.5, color="0.35")

    def scan_labels(ax):
        for r in range(3):
            ax.text(-0.4, -r + 0.5, f"scan {r}", ha="right", va="center",
                    fontsize=8, color="0.4")

    def between_peaks(ax, x):
        ax.text(x + peakgap / 2.0, -1.5, "//  ⋯  //", ha="center",
                va="center", fontsize=10, color="0.6")

    # --- Profile: each of the two peaks is MANY points -> many staircases. ---
    x = draw_peak(axp, 0, 3)
    peak_label(axp, 0, x, "peak 1")
    between_peaks(axp, x)
    x2 = draw_peak(axp, x + peakgap, 3)
    peak_label(axp, x + peakgap, x2, "peak 2")
    scan_labels(axp)
    axp.set_aspect("equal")
    axp.set_xlim(-4.0, x2 + 0.5)
    axp.set_ylim(-3.2, 1.7)
    axp.axis("off")
    axp.set_title("(a) Profile, binned", fontsize=10.5, pad=12)
    axp.text(x2 / 2.0, -2.9,
             "each peak = MANY points = a row of staircases "
             "(// = dropped bins), ~2/3 zeros",
             ha="center", va="top", fontsize=8.5, color="0.3")

    # --- Centroid: each of the SAME two peaks is ONE point -> one staircase. ---
    staircase(axc, 0)
    peak_label(axc, 0, 3, "peak 1")
    between_peaks(axc, 3)
    staircase(axc, 3 + peakgap)
    peak_label(axc, 3 + peakgap, 6 + peakgap, "peak 2")
    scan_labels(axc)
    axc.set_aspect("equal")
    axc.set_xlim(-4.0, x2 + 0.5)                 # same scale as (a): equal cells
    axc.set_ylim(-3.2, 1.7)
    axc.axis("off")
    axc.set_title("(b) Centroid, binned", fontsize=10.5, pad=12)
    axc.text((6 + peakgap) / 2.0, -2.9,
             "each peak = ONE point = one staircase, "
             "far fewer columns, ~2/3 zeros",
             ha="center", va="top", fontsize=8.5, color="0.3")
    fig.text(0.5, 0.04,
             "blue = a scan's nonzero value     0 = zero     "
             "// = dropped empty bins",
             ha="center", va="bottom", fontsize=8, color="0.4")
    _save(fig, "centroid_zeros.svg")


def bin_realign():
    """ Why a coarse enough grid removes the zeros. One measured point, sampled by
    three drifting scans. A bin narrower than the drift puts the three in separate
    bins (three columns, two thirds zeros); a bin wider than the drift catches all
    three in one bin (one column, no zeros). """
    fig, (ax_f, ax_w) = plt.subplots(1, 2, figsize=(8.8, 3.7))
    colors = [BLUE, GREEN, ORANGE]
    pts = [1.3, 1.5, 1.7]                      # three scans' drifted m/z (schematic)

    def panel(ax, bins, cols, title, sub):
        for (lo, hi) in bins:                  # shaded bins (the grid)
            ax.add_patch(Rectangle((lo, 0.0), hi - lo, 1.0, facecolor="0.95",
                                   edgecolor="0.8", lw=0.8, zorder=0))
        for s, x in enumerate(pts):            # the three drifting points
            ax.vlines(x, 0, 0.78, color=colors[s], lw=2.2, zorder=3)
            ax.scatter([x], [0.78], s=30, color=colors[s], zorder=4)
        ax.annotate("", xy=(pts[0], 1.16), xytext=(pts[2], 1.16),
                    arrowprops=dict(arrowstyle="<->", color="0.45", lw=1.0))
        ax.text(pts[1], 1.22, "the same m/z, recorded by\nthree drifting scans",
                ha="center", va="bottom", fontsize=7.5, color="0.45")
        left = min(b[0] for b in bins)
        for (lo, hi, fill) in cols:            # resulting matrix columns
            for s in range(3):
                y = -0.55 - 0.6 * s
                has = s in fill
                ax.add_patch(Rectangle((lo, y), hi - lo, 0.5, fill=has,
                             facecolor=colors[s] if has else "white",
                             alpha=0.45 if has else 1.0, edgecolor="0.5"))
                if not has:
                    ax.text((lo + hi) / 2.0, y + 0.25, "0", color=RED,
                            ha="center", va="center", fontsize=9, weight="bold")
        for s in range(3):
            ax.text(left - 0.08, -0.55 - 0.6 * s + 0.25, f"scan {s}", ha="right",
                    va="center", fontsize=7.5, color=colors[s])
        ax.set_xlim(0.55, 2.45)
        ax.set_ylim(-2.5, 1.55)
        ax.axis("off")
        ax.set_title(title, fontsize=10)
        ax.text(pts[1], -2.4, sub, ha="center", va="top", fontsize=8.3,
                color="0.3")

    panel(ax_f, [(1.2, 1.4), (1.4, 1.6), (1.6, 1.8)],
          [(1.2, 1.4, {0}), (1.4, 1.6, {1}), (1.6, 1.8, {2})],
          "(a) bin narrower than the drift",
          "three scans land in three bins:\nthree columns, two thirds zeros")
    panel(ax_w, [(1.0, 2.0)], [(1.0, 2.0, {0, 1, 2})],
          "(b) bin wider than the drift",
          "three scans land in one bin:\none column, no zeros")
    _save(fig, "bin_realign.svg")


def _amber_profile_grid(bin_width, lo, hi):
    """ Read the real amber.D fixture (a 500-scan, m/z-windowed slice of a real
    Q-TOF run; run-length encoded, so no lzf), bin its profile, and place the
    occupied columns on a uniform m/z grid over [lo, hi) (0 elsewhere) so it can
    be drawn as a literal heatmap. """
    import sys
    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    import rainbow as rb
    f = rb.read(os.path.join(_REPO, "tests", "inputs", "amber.D"),
                hrms=True, bin_width=bin_width).get_file("MSProfile.bin")
    yl = np.asarray(f.ylabels)
    n = int(round((hi - lo) / bin_width))
    grid = np.zeros((f.data.shape[0], n))
    for c in range(yl.size):
        j = int(round((yl[c] - lo) / bin_width))
        if 0 <= j < n and lo <= yl[c] < hi:
            grid[:, j] = f.data[:, c]
    return grid


def worked_example():
    """ The worked example as literal heatmaps (imshow) of a real 500-scan Q-TOF
    run (amber.D), binned near m/z 825.42. Rows are scans (retention time),
    columns are m/z, colour (log) is intensity, and zeros (a bin no scan filled,
    or a scan that sampled elsewhere) are masked grey. The fine grid leaves a comb
    of grey gaps; the coarse grid fills them. The bright horizontal band is the
    analyte eluting off the column at one retention time. """
    from matplotlib.colors import LogNorm
    from matplotlib.patches import Patch
    lo, hi = 825.30, 825.55
    fine = _amber_profile_grid(0.005, lo, hi)
    coarse = _amber_profile_grid(0.05, lo, hi)
    ns = fine.shape[0]
    apex = int(fine.sum(axis=1).argmax())                 # elution scan
    vmax = fine.max()
    norm = LogNorm(vmin=max(fine[fine > 0].min(), vmax / 300), vmax=vmax)

    fig, (axf, axc) = plt.subplots(1, 2, figsize=(9.0, 4.4),
                                   gridspec_kw=dict(width_ratios=[1, 1]),
                                   constrained_layout=True)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("0.85")                                  # zeros -> grey

    def heat(ax, grid, title):
        im = ax.imshow(np.ma.masked_equal(grid, 0), aspect="auto", cmap=cmap,
                       norm=norm, extent=[lo, hi, ns, 0],
                       interpolation="nearest")
        ax.set_xlabel("m/z (Da)", fontsize=9)
        ax.set_xticks([825.35, 825.45, 825.55])
        ax.set_title(title, fontsize=9.5)
        ax.tick_params(labelsize=8)
        return im

    im = heat(axf, fine, "(a) fine grid (0.005 Da):\ncomb of grey gaps (zeros)")
    axf.set_ylabel("scan index (retention time)", fontsize=9)
    axf.annotate("analyte elutes\n(bright band)", xy=(hi, apex),
                 xytext=(hi + 0.02, apex), ha="left", va="center",
                 fontsize=7.5, color=RED,
                 arrowprops=dict(arrowstyle="->", color=RED))
    heat(axc, coarse, "(b) coarse grid (0.05 Da):\ngaps filled (realigned)")
    axc.set_yticklabels([])
    # grey = 0 key
    axf.legend(handles=[Patch(facecolor="0.85", edgecolor="0.5",
                              label="grey = 0 (empty bin, no signal)")],
               loc="upper left", bbox_to_anchor=(0.0, -0.16), fontsize=8,
               frameon=False)
    cb = fig.colorbar(im, ax=(axf, axc), fraction=0.05, pad=0.03)
    cb.set_label("intensity (log)", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    _save(fig, "worked_example.svg", tight=False)


if __name__ == "__main__":
    centroid_vs_profile()
    data_rectangle()
    mz_drift()
    shared_grid_zeros()
    bin_realign()
    centroid_zeros()
    worked_example()
    print("wrote:", ", ".join(sorted(
        f for f in os.listdir(HERE) if f.endswith(".svg"))))
