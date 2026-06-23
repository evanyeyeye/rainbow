.. _hrms-data-model:

HRMS Profile Data Model (m/z is per-scan)
=========================================

This page explains how **rainbow** represents high-resolution mass-spectrometry
(HRMS) profile data, and why that representation is unusual. The byte-level
layout of the file itself is documented separately in :ref:`MSProfile.bin <hrms>`.

A few terms first
-----------------

- **Scan**: one spectrum, measured at one instant during a run. A run is a
  sequence of scans, indexed by ``i`` (``i`` increases with time).
- **Spectrum**: a curve of **intensity** (how much signal was seen) versus
  **m/z** (the mass-related x-value, in daltons, ``Da``).
- **Point index** ``j``: within one scan the measured values are a list of
  length ``k``, indexed by ``j`` from ``0`` to ``k-1``.
- **Profile vs. centroid**: a *profile* scan stores the whole curve (~100,000
  points), a quasi-continuous trace. A *centroid* scan stores only the handful
  of detected peak positions, so it is short. This page is about profile data;
  centroids are covered briefly at the end.

The intensities are a clean rectangle
-------------------------------------

For profile data the intensities line up into a 2-D array: one row per scan
``i``, one column per point ``j``.

.. figure:: figures/data_rectangle.svg
   :width: 80%
   :align: center

   Each cell holds one intensity value, ``data[i][j]``.

So the *intensities* fit a normal table. The difficulty is the m/z.

The m/z depends on the scan, not just the point
-----------------------------------------------

Every scan is sampled on the same raw instrument clock, the **time of flight**
(TOF). Point ``j`` corresponds to the same flight-time value ``tof[j]`` in every
scan, so column ``j`` is the *same physical measurement* in every row of the
rectangle.

To turn a flight time into an m/z, the instrument uses a few fitted numbers
called a **calibration**. Because instrument conditions change slowly during a
run, the calibration is re-fit for each scan and shifts over time; this shift is
called **drift**. The consequence is that the *same* point ``j`` is assigned a
slightly *different* m/z in different scans.

.. figure:: figures/mz_drift.svg
   :width: 75%
   :align: center

   A fixed point index has the same flight time in every scan, but its m/z
   drifts as the calibration changes. Over a full run the drift (~0.024 Da here)
   is larger than the spacing to the neighbouring point (~0.016 Da), so a point
   slides past where its neighbour started.

Because the drift is larger than the spacing between points, **there is no single
m/z axis that is correct for every scan**. The m/z is a function of *both*
indices: the scan ``i`` and the point ``j``.

rainbow therefore does not store an m/z for every cell. It keeps the shared
flight-time axis ``tof`` (one value per point, identical for all scans) plus each
scan's short list of calibration numbers, and computes a scan's m/z on demand.
Only one of those calibration numbers changes from scan to scan, so this is both
exact and tiny: instead of a full m/z for all ~100,000 points of every scan, it
stores one flight-time array plus a few numbers per scan.

Why one shared m/z axis loses data
----------------------------------

You may still want a single shared m/z axis, so that every scan lines up into one
rectangle you can index by m/z, for example to pull out the signal at one m/z
over time (an *extracted-ion chromatogram*), draw a heatmap, or sum the scans in
a time window. To build it you must round every m/z to a common grid so that
nearby values from different scans fall in the same column. That rounding inserts
**zeros**, for two reasons.

First, the grid is **uniform**, but the real points are **not** evenly spaced,
and the grid is finer than the real spacing. So within a single scan, grid
columns fall *between* the real points and receive nothing. A grid column that no
point lands in is filled with intensity 0, a value that was never actually
measured.

.. figure:: figures/shared_grid_zeros.svg
   :width: 85%
   :align: center

   One scan's real points (~0.016 Da apart, blue) on a uniform 0.01 Da grid. The
   grid columns that no point falls into become inserted zeros (red).

Second, **drift** puts the same point in different grid columns in different
scans. So the shared axis has to include every column that *any* scan uses (the
**union** of all the scans' occupied columns), which is far more columns than any
single scan fills. On one real dataset a scan has ~105,000 points, but the union
over 1256 drifting scans is ~249,000 columns, so any single scan is
``1 - 105,000 / 249,000``, about **58% zeros**.

The counter-intuitive part: a **finer** grid makes this **worse**, not better.
Finer columns mean fewer scans share a column, so the union grows and the rows
get emptier. No decimal precision avoids it: a coarse grid loses resolution by
merging nearby peaks, a fine grid floods the rows with zeros. The zeros come from
forcing one shared axis, not from the data.

How rainbow represents profile data
-----------------------------------

**Per-scan and unbinned, by default.** rainbow keeps the intensity rectangle
``data[i][j]`` as-is (no rounding, no inserted zeros) and exposes the m/z through
methods that **require a scan index**, so you can never accidentally read an m/z
that is only approximately right for a given scan:

.. code-block:: python

   df.scan(i)         # -> (m/z array, intensity array) for scan i
   df.mass_labels(i)  # -> the m/z array for scan i
   df.tof             # the shared flight-time axis (same for every scan)
   df.data            # the 2-D intensities, shape (num_scans, k)

There is deliberately **no** ``df.ylabels`` (the attribute other rainbow files
use for their single y-axis). A profile has no single m/z axis, so reading
``ylabels`` raises an error that points you to ``mass_labels(i)`` / ``scan(i)``
rather than returning something subtly wrong.

**The shared grid is still available, but opt-in.** When you genuinely want the
rectangular m/z-by-time matrix, you ask for it explicitly and accept that it is a
lossy projection (it inserts the zeros above and merges nearby points).

Choosing precision
------------------

``prec`` is the number of decimal places m/z is rounded to. It is used in two
different places that must not be confused:

.. list-table::
   :widths: 26 14 60
   :header-rows: 1

   * - Where
     - Default
     - Why
   * - Per-scan m/z labels
     - 4 decimals
     - Sets only how many digits ``mass_labels(i)`` reports. Each scan keeps its
       own labels, so rounding them never forces two scans to share a column; it
       cannot create zeros or merge points. Four decimals reflects how precisely
       the instrument knows each mass.
   * - Opt-in shared grid
     - 0.01 Da
     - The bin width of the projected matrix. 0.01 Da does not remove the zeros
       (nothing does), but it is coarse enough that the ~0.024 Da drift rarely
       crosses a bin boundary, while still keeping most real peaks apart.

Do not round the shared grid to whole numbers (``prec=0``, "nominal mass"): that
collapses every m/z to an integer and merges distinct high-resolution peaks. And
do not make it very fine (such as 0.0001 Da): that is the zero-flooding case
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
