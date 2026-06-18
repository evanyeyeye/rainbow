"""
Generates the SVG diagrams for the Performance page (docs/source/performance.rst).

Run from this directory:  python3 make_perf_diagrams.py
Each figure contrasts the slow and the fast way. Committed as static assets so
the docs build needs no extra tooling.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK = "#2f3338"
EDGE = "#6b7a99"
FILL = "#eef1f7"
HI = "#ffe1b0"
HIE = "#d08a2e"
GREEN = "#dcecdc"
GREENE = "#5f9a6f"
MUTE = "#9aa3b0"
SLOW = "#b5651d"
FAST = "#3f7d4f"
plt.rcParams.update({"font.size": 12, "svg.fonttype": "path",
                     "font.family": "DejaVu Sans"})


def box(ax, x, y, w, h, t="", fc=FILL, ec=EDGE, fs=11, bold=False, tc=INK, mono=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=0.06", fc=fc, ec=ec, lw=1.3))
    if t:
        # Trim the text a touch so it never crowds the border.
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=fs * 0.88,
                color=tc, fontweight="bold" if bold else "normal",
                family="monospace" if mono else None)


def arr(ax, p1, p2, c=MUTE, lw=1.6):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=13,
                                 color=c, lw=lw, shrinkA=2, shrinkB=2))


def label(ax, x, y, t, color, fs=12):
    ax.text(x, y, t, fontsize=fs, color=color, fontweight="bold", va="center")


def newax(w, h, xlim, ylim):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.savefig(name, bbox_inches="tight", transparent=True, pad_inches=0.08)
    plt.close(fig)


def record(ax, x, y, w, h, tlabel):
    """[ ... | <field> | ... ], the wanted field highlighted."""
    s, m = 0.32 * w, 0.36 * w
    box(ax, x, y, s, h, "...", fc="#f4f4f4", ec="#cccccc", fs=12, tc="#aaa")
    box(ax, x + s, y, m, h, tlabel, fc=HI, ec=HIE, fs=10, bold=True)
    box(ax, x + s + m, y, s, h, "...", fc="#f4f4f4", ec="#cccccc", fs=12, tc="#aaa")


# =============================================================== strided view
fig, ax = newax(8.4, 4.2, (0, 17), (0, 8.6))
ax.text(0.2, 8.2, "a record holds several fields (\"...\" = other bytes); "
        "we want one field (the time) from each", fontsize=11, color=INK)

label(ax, 0.3, 7.2, "SLOW: Python loop, one record at a time", SLOW)
for i in range(3):
    rx = 0.5 + i * 3.3
    record(ax, rx, 5.7, 2.9, 0.78, f"time{i}")
    box(ax, rx + 0.95, 4.3, 1.0, 0.66, f"time{i}", fc=HI, ec=HIE, fs=10, bold=True)
    arr(ax, (rx + 1.45, 5.68), (rx + 1.45, 5.0), c=SLOW)
    ax.text(rx + 1.75, 5.32, f"step {i+1}", color=SLOW, fontsize=8.5, va="center")
ax.text(11.2, 4.62, "append one at a time", color="#888", fontsize=10, va="center")

label(ax, 0.3, 3.4, "FAST: one strided NumPy view over the whole buffer", FAST)
for i in range(3):
    rx = 0.5 + i * 3.3
    record(ax, rx, 1.9, 2.9, 0.78, f"time{i}")
for i in range(3):
    box(ax, 11.0 + i * 1.5, 1.95, 1.4, 0.68, f"time{i}", fc=HI, ec=HIE, fs=10, bold=True)
arr(ax, (10.2, 2.28), (10.9, 2.28), c=FAST, lw=2.2)
ax.text(5.4, 1.1, "np.ndarray(n, '<u4', buf, offset=4, strides=22)",
        color=FAST, fontsize=10, ha="center", family="monospace")
save(fig, "perf_strided.svg")


# =================================================================== binning
fig, ax = newax(8.4, 4.9, (0, 15), (0, 9.8))
ax.text(0.2, 9.4, "one scan: (m/z, value) pairs, with m/z 100 and 102 repeated",
        fontsize=11, color=INK)
pairs = [(100, 3), (102, 5), (101, 9), (102, 7), (100, 4)]
pcol = {100: "#ffd9b0", 101: GREEN, 102: "#cfdcf5"}
for i, (m, v) in enumerate(pairs):
    box(ax, 1.6 + i * 1.55, 8.3, 1.4, 0.78, f"{m}: {v}", fc=pcol[m], ec="#9aa6bb", fs=11)

box(ax, 0.5, 5.25, 5.0, 1.0, "np.unique + searchsorted\nsorts all N points",
    fc="#fbeeee", ec=SLOW, fs=10.5)
box(ax, 8.1, 5.25, 6.4, 1.0, "histogram the integer bins, then rank\none pass, no sort",
    fc="#eef6ef", ec=FAST, fs=10.5)
ax.text(3.0, 6.6, "SLOW: sort", color=SLOW, fontsize=12, fontweight="bold", ha="center")
ax.text(11.3, 6.6, "FAST: histogram", color=FAST, fontsize=12, fontweight="bold", ha="center")
arr(ax, (4.1, 8.25), (4.9, 6.3), c=SLOW)
arr(ax, (6.7, 8.25), (8.6, 6.3), c=FAST)

cells = [(100, 7, "3 + 4"), (101, 9, "9"), (102, 12, "5 + 7")]
for j, (m, v, agg) in enumerate(cells):
    cx = 3.3 + j * 2.8
    box(ax, cx, 2.7, 2.6, 1.0, f"m/z {m}\n{v}", fc=pcol[m], ec="#7a8aa8",
        fs=11, bold=True)
    ax.text(cx + 1.3, 2.35, agg, fontsize=9.5, color="#888", ha="center")
arr(ax, (2.8, 5.2), (4.6, 3.75), c=SLOW)
arr(ax, (11.2, 5.2), (9.5, 3.75), c=FAST)
ax.text(7.05, 1.6, "one row of the (time x m/z) matrix for this scan",
        fontsize=11, color=INK, ha="center")
save(fig, "perf_binning.svg")


# ==================================================================== lookup
fig, ax = newax(8.4, 3.8, (0, 15.5), (0, 7.8))
ax.text(0.2, 7.4, "Agilent .ms intensities span a wide range, so each is stored "
        "as  value x 8 ** head  (head = a 2-bit exponent, 0..3)",
        fontsize=10.5, color=INK)

# both rows: head = 2  ->  [mechanism]  ->  64
label(ax, 0.4, 6.3, "SLOW: evaluate the function for every value", SLOW)
box(ax, 0.6, 4.9, 1.9, 0.85, "head = 2", fc=HI, ec=HIE, fs=11, bold=True)
box(ax, 4.0, 4.9, 2.2, 0.85, "8 ** head", fc="#fbeeee", ec=SLOW, fs=12, bold=True, mono=True)
box(ax, 7.8, 4.9, 1.3, 0.85, "64", fc=FILL, ec=EDGE, fs=12, bold=True)
arr(ax, (2.55, 5.32), (3.95, 5.32), c=SLOW)
arr(ax, (6.25, 5.32), (7.75, 5.32), c=SLOW)
ax.text(10.2, 5.32, "done N times", color="#888", fontsize=10, va="center")

label(ax, 0.4, 3.4, "FAST: precompute the 4 results once, then index", FAST)
box(ax, 0.6, 2.0, 1.9, 0.85, "head = 2", fc=HI, ec=HIE, fs=11, bold=True)
tab = [(0, 1), (1, 8), (2, 64), (3, 512)]
tx = 4.0
for j, (idx, val) in enumerate(tab):
    sel = idx == 2
    box(ax, tx + j * 1.25, 2.0, 1.15, 0.85, f"{val}", fc=HI if sel else FILL,
        ec=HIE if sel else EDGE, fs=12, bold=True)
    ax.text(tx + j * 1.25 + 0.575, 1.66, f"{idx}", color="#888", fontsize=9, ha="center")
box(ax, 11.6, 2.0, 1.3, 0.85, "64", fc=FILL, ec=EDGE, fs=12, bold=True)
arr(ax, (2.55, 2.42), (3.95, 2.42), c=FAST)
arr(ax, (tx + 4 * 1.25, 2.42), (11.55, 2.42), c=FAST)
ax.text(7.0, 1.05, "table[2] = 64    (one read, no exponentiation)", color=FAST,
        fontsize=9.5, ha="center")
save(fig, "perf_lookup.svg")


# ===================================================================== delta
fig, ax = newax(9.4, 2.9, (0, 19.6), (0, 5.6))
ax.text(0.2, 5.2, "each entry is a delta added to a running total, except a "
        "sentinel that resets it to an absolute value", fontsize=11, color=INK)
ax.text(0.2, 4.5, "SEQUENTIAL: every step needs the previous total, so it cannot "
        "be vectorized (hence the compiled loop)", fontsize=10.5, color=SLOW)
accs = [("0", False), ("5", False), ("15", False), ("1000", True),
        ("996", False), ("998", False)]
deltas = [("+5", False), ("+10", False), ("reset\n1000", True), ("-4", False), ("+2", False)]
ay, ah, aw = 0.7, 0.92, 1.7
axs = [0.3 + i * 3.15 for i in range(6)]
for i, (a, sent) in enumerate(accs):
    fc = "#f1f1f1" if i == 0 else (HI if sent else "#eef6ee")
    ec = "#bbb" if i == 0 else (HIE if sent else GREENE)
    box(ax, axs[i], ay, aw, ah, f"acc\n{a}", fc=fc, ec=ec, fs=10, bold=True)
for i in range(5):  # running total carried left to right
    arr(ax, (axs[i] + aw, ay + ah / 2), (axs[i + 1], ay + ah / 2), c="#b9c0cc", lw=1.7)
dy, dh, dw = 2.9, 0.92, 1.7
for i, (d, sent) in enumerate(deltas):  # delta applied, straight down into the new acc
    dx = axs[i + 1]
    box(ax, dx, dy, dw, dh, d, fc=HI if sent else FILL, ec=HIE if sent else EDGE,
        fs=11, bold=sent)
    arr(ax, (dx + dw / 2, dy), (dx + dw / 2, ay + ah), c=HIE if sent else MUTE)
save(fig, "perf_delta.svg")

print("wrote perf_strided/binning/lookup/delta .svg")
