.. _hrms-data-model:

HRMS Profile Data Model (m/z is per-scan)
=========================================

This page explains how **rainbow** represents high-resolution mass-spectrometry
(HRMS) profile data, and why that representation is unusual. We will see (1) what
profile data is, (2) why a high-resolution time-of-flight instrument gives every
scan its *own* m/z sampling, and (3) why forcing all the scans onto one shared
m/z axis loses data. The byte-level layout of the file is documented separately
in :ref:`MSProfile.bin <hrms>`.

A few terms
-----------

- **Scan**: one spectrum, measured at one instant during a run. A run is a
  sequence of scans, indexed by ``i`` (``i`` increases with time).
- **Spectrum**: a curve of **intensity** (how much signal was seen) versus
  **m/z** (mass-to-charge ratio, a mass-like x-axis, measured in daltons,
  ``Da``, a unit of mass).
- **Point index** ``j``: within one scan the measured values are a list of
  length ``k``, indexed by ``j`` from ``0`` to ``k-1``.

Profile vs. centroid
--------------------

A scan can be stored in two forms. A **profile** scan keeps the whole measured
curve, roughly 100,000 points (about 105,000 in the worked example below),
sampled densely across the m/z range. A **centroid** scan keeps only the handful
of detected peak positions, so it is short. This page is about **profile** data;
centroids are revisited at the end.

Why each scan has its own m/z
-----------------------------

A mass spectrometer reports intensity as a function of m/z, but *how* it arrives
at the m/z axis depends on the instrument, and that difference is the whole reason
profile data is awkward.

A **time-of-flight** (TOF) instrument does not measure m/z directly. It gives
every ion the same energy and times how long each takes to reach the detector:
lighter ions arrive sooner, heavier ones later. So what it actually records is
intensity at a ladder of **flight times**, fixed by the instrument clock. Flight
time ``j`` is the *same physical measurement* in every scan, the same tick
``tof[j]``. To convert a flight time into an m/z, the instrument applies a few
fitted numbers, a **calibration**, and it re-fits that calibration every scan to
track conditions such as temperature.

Because the calibration changes slightly from scan to scan, the same flight tick
``j`` is converted to a slightly different m/z in different scans. Stated
carefully, this is **not** that any mass moves (a 100 Da ion is always 100 Da);
it is that **different scans collect their data at different m/z positions**: one
scan happens to sample near 100.00 Da, a later scan near 100.05 Da. There is no
m/z value that every scan lands on.

**Drift** is the slow, roughly linear change, over a run, in the m/z that the
calibration assigns to a fixed flight time.

.. figure:: figures/mz_drift.svg
   :width: 62%
   :align: center

   The m/z assigned to one fixed flight time, across the run. It moves by about
   0.024 Da, more than the ~0.016 Da gap between adjacent points in a scan, so
   successive scans sample noticeably different m/z positions.

A **unit-resolution** instrument such as a **quadrupole** or **triple quadrupole**
(QQQ) works the opposite way. It is *commanded* to transmit a chosen m/z and
steps through a fixed list of m/z targets, usually every integer mass, and every
scan uses that same list. Its m/z axis is decided up front and is identical for
all scans, so a single shared axis is already correct and none of the problems
below arise. The trade-off is resolution: it only separates masses about a whole
unit apart. A high-resolution TOF buys fine mass accuracy at the cost of giving
each scan its own m/z sampling.

So the principle rainbow follows is: **when different scans collect their data at
different m/z positions, no single m/z axis is correct for every scan.** The m/z
is then a function of *both* indices, the scan ``i`` and the point ``j``.

Intensities are a full rectangle; m/z is not shared
---------------------------------------------------

The *intensities* are the easy part: every scan has the same number of points
``k``, so they form a **full rectangle**, one row per scan and one column per
point, with no ragged rows of differing length.

.. figure:: figures/data_rectangle.svg
   :width: 66%
   :align: center

   The intensities line up into a full rectangle. But the m/z that labels a given
   column is *not* shared: scan 0 and scan 1200 read different m/z at the same
   column. That mismatch is what the rest of this page is about.

rainbow does not store an m/z for every cell. It keeps the shared flight-time
axis ``tof`` (one value per point, identical for all scans) plus each scan's
short list of calibration numbers, and computes a scan's m/z on demand. Only one
of those calibration numbers changes from scan to scan, so this is both exact and
tiny: instead of a full m/z for all ~105,000 points of every scan, it stores one
flight-time array plus a few numbers per scan.

Why one shared m/z axis loses data
----------------------------------

You may still want a single shared m/z axis, so that every scan lines up into one
rectangle you can index by m/z (for example to pull out the signal at one m/z over
time, draw a heatmap, or sum the scans in a time window). To build it, rainbow
rounds each scan's m/z values onto a common grid of evenly spaced **bins** (0.01
Da wide by default) and keeps **only the bins that at least one scan lands in**.
The shared axis is the **union** of every scan's occupied bins; bins that no scan
ever fills are not created.

That last detail rules out the gaps *within* a single scan as a source of zeros.
The points in one scan sit about 0.016 Da apart, wider than the 0.01 Da bins, so
consecutive points land in **non-adjacent** bins, leaving an empty bin or two
between them. (A point never falls "between" bins; every point lands in some bin.
The empty bins are the ones *between* the occupied ones.) But because rainbow
drops bins that no scan occupies, those within-scan gaps never reach the output.
If every scan sampled the same m/z positions, the union would equal one scan's
bins and the rectangle would have **no zeros at all**.

The zeros come from one thing: **drift**. Because different scans sample at
different m/z positions, they occupy *different* bins, and the union of all of
them has many more bins than any single scan fills. Each scan then reads **0** in
the bins that only *other* scans occupied.

.. figure:: figures/shared_grid_zeros.svg
   :width: 70%
   :align: center

   Two scans sample at slightly different m/z (top), so they occupy different bins
   of the shared grid (bottom). Each scan reads 0 (red) in the bins only the other
   scan filled.

On one real dataset a scan has about 105,000 occupied bins, but the union over
1256 drifting scans is about 249,000 bins, so a single scan is
``1 - 105,000 / 249,000``, about **58% zeros**.

A **finer** grid makes this worse, and it is the same effect, not a new one:
narrower bins mean a given drift more often pushes a point into a different bin
than its counterpart in another scan, so the scans share fewer bins, the union
grows, and the rows get emptier. No bin width escapes the trade-off; a coarse grid
merges real peaks and a fine grid floods the rows with zeros, because the zeros
come from forcing one axis onto scans that never shared one.

How rainbow represents profile data
-----------------------------------

**Per-scan and unbinned, by default.** rainbow keeps the intensity rectangle
``data[i][j]`` as-is (no rounding, no inserted zeros) and exposes the m/z through
methods that **require a scan index**, so you can never accidentally read an m/z
that is only approximately right for a given scan:

.. code-block:: python

   profile.scan(i)         # -> (m/z array, intensity array) for scan i
   profile.mass_labels(i)  # -> the m/z array for scan i
   profile.tof             # the shared flight-time axis (same for every scan)
   profile.data            # the 2-D intensities, shape (num_scans, k)

There is deliberately **no** ``profile.ylabels`` (the attribute other rainbow
files use for their single y-axis). A profile has no single m/z axis, so reading
``ylabels`` raises an error that points you to ``mass_labels(i)`` / ``scan(i)``
rather than returning something subtly wrong.

**The shared grid is still available, but opt-in.** When you genuinely want the
rectangular m/z-by-time matrix, you ask for it explicitly and accept that it is a
lossy projection (it inserts the zeros above and merges nearby points).

Choosing precision
------------------

``prec`` (the number of decimal places m/z is rounded to) appears in two
**unrelated** places, which must not be confused:

.. list-table::
   :widths: 26 14 60
   :header-rows: 1

   * - Where
     - Default
     - Why
   * - Per-scan m/z labels
     - 4 decimals
     - Sets only how many digits ``mass_labels(i)`` reports. Each scan keeps its
       own labels, so rounding them never forces two scans to share a bin; it
       cannot create zeros or merge points. Four decimals reflects how precisely
       the instrument knows each mass.
   * - Opt-in shared grid
     - 0.01 Da
     - The bin width of the projected matrix. It does not remove the zeros
       (nothing does); it is a common compromise, narrow enough to keep most real
       peaks in separate bins, wide enough to keep the number of bins manageable.

Do not round the shared grid to whole numbers (``prec=0``, "nominal mass", i.e.
m/z rounded to the nearest integer): that merges distinct high-resolution peaks.
And do not make it very fine (such as 0.0001 Da): that is the zero-flooding case
above. The 4-decimal default belongs to the per-scan labels, not to the grid.

A note on centroids
-------------------

Centroids are already short lists of peaks, so binning them onto a shared grid is
reasonable, and combining peaks across scans onto one axis is a normal operation
(a merged spectrum, or one peak's chromatogram over time). But binning still
rounds each peak's m/z to the bin width, and the default whole-number precision
would round high-resolution peaks to integer mass and merge real ones. So prefer
the raw per-scan peak lists for centroids too, and treat binning as an explicit
choice with a precision finer than nominal mass.
