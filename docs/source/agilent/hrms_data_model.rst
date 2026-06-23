.. _hrms-data-model:

HRMS Profile Data Model (m/z is per-scan)
=========================================

High-resolution profile data does not fit the rectangular "one shared y-axis"
model that works for UV, nominal-mass MS, and most other detectors. This page
explains why, and how **rainbow** represents it. The byte-level layout of the
file is documented separately in :ref:`MSProfile.bin <hrms>`.

Profile vs. centroid
--------------------

A Q-TOF (or similar high-resolution) acquisition can store two different views
of each scan:

- **Profile**: the full sampled trace, roughly 100,000 points per scan, a
  quasi-continuous curve. This is the detailed spectrum.
- **Centroid**: the peak-picked result, a short list of ``(m/z, intensity)``
  pairs, one per detected peak. This is sparse.

The data-model issue below is about **profile** data. Centroids are discussed at
the end.

m/z is a function of *two* indices
----------------------------------

Index a scan by ``i`` (increasing with retention time) and a point within a scan
by ``j`` (``0 .. k-1``). The intensities form a clean rectangle:

.. code-block:: text

                       point index  j  ->
                 0       1       2      ...     k-1
   scan i=0   [ I00 ] [ I01 ] [ I02 ]  ...  [ I0,k-1 ]
   scan i=1   [ I10 ] [ I11 ] [ I12 ]  ...  [ I1,k-1 ]
   scan i=2   [ I20 ] [ I21 ] [ I22 ]  ...  [ I2,k-1 ]
     ...
              <-------------- data[i][j] ------------->

The catch is the m/z. Each scan is sampled on the **same** raw flight-time grid
(``tof[j] = start + delta * j``, identical for every scan), so point ``j`` is the
same physical measurement bin in every scan. But the conversion from flight time
to m/z is **calibrated per scan**, and that calibration **drifts** over a run. So
the m/z of point ``j`` depends on the scan too:

.. code-block:: text

   index j = 52000,  TOF = 69552.0   (identical in every scan)
       scan   84:  m/z = 1556.3593
       scan 1255:  m/z = 1556.3543      <- same point, drifted ~0.005 Da

Across a full run the drift reaches ~0.024 Da (about 8 ppm), which is **larger
than the spacing between adjacent points** (~0.014-0.029 Da). So there is no
single 1-D m/z axis that is correct for every scan. The m/z is genuinely a 2-D
quantity:

.. code-block:: text

   ylabel(i, j) = calibrate( tof[j], calib[i] )

Internally **rainbow** does not store a 2-D m/z array. Only one of the ten
calibration numbers (the scale factor ``coeff``) changes from scan to scan; the
rest are constant for the run. So the whole axis factors, and reconstructs
exactly:

.. code-block:: text

   ylabel(i, j) = coeff[i]**2 * u2[j]  -  poly[j]

       u2[j]   = (tof[j] - base)**2      shared 1-D array, length k
       poly[j] = polynomial(tof[j])      shared 1-D array, length k
       coeff[i]                          ONE scalar per scan

That is one shared axis plus one number per scan, rather than a m/z for every
cell.

Why a single shared axis loses data
------------------------------------

To force every scan onto one shared 1-D m/z axis, you must round m/z to a common
grid so different scans share columns. Two things then create spurious zeros.

First, the grid is **uniform** but the real points are **not**, and the grid is
finer than the data's own spacing, so each scan has empty columns between its
own points:

.. code-block:: text

   actual points (spacing ~0.016 Da):    *       *       *       *
   uniform 0.01 Da grid columns:         | | | | | | | | | | | | | |
   scan mapped onto the grid:            * 0 * 0 0 * 0 0 * 0 0 * 0 0   <- zeros

Second, the per-scan drift means the **same** point lands in a **different**
column in different scans. Pooling many scans onto one axis fills far more
columns than any single scan occupies, so every scan is sparse on the union:

.. code-block:: text

   one scan occupies   ~105,152 points
   shared axis (union) ~249,155 columns      <- pooled over 1256 drifting scans
   => any single scan is ~58% zeros

The key, counter-intuitive consequence: a **finer** grid makes this **worse**,
not better. Finer bins mean fewer scans share a column, so the union grows and
the rows become emptier. There is no decimal precision that fixes it; coarse
loses resolution by merging peaks, fine floods zeros. The zeros are a property of
the shared-grid representation, not of the data.

How rainbow represents profile data
-----------------------------------

**Per-scan and unbinned, by default.** The intensities are kept as the rectangle
``data[i][j]`` (no rounding, no inserted zeros), and the m/z is exposed through
accessors that **require a scan index**, so a caller can never silently read an
approximate axis:

.. code-block:: text

   df.scan(i)         -> (mass_labels, intensities) for scan i  (the per-scan spectrum)
   df.mass_labels(i)  -> exact m/z array for scan i  =  coeff[i]**2 * u2 - poly
   df.tof             -> the shared flight-time / point-index axis (same every scan)
   df.data            -> 2-D intensities, shape (num_scans, k)

There is deliberately **no** ``df.ylabels`` returning m/z for a profile: a single
m/z column does not exist, so the attribute raises with a message pointing at
``mass_labels(i)``/``scan(i)`` rather than returning something wrong.

**Gridding is an opt-in projection.** When you actually want a rectangular
retention-time by m/z matrix (for an extracted-ion chromatogram, a heatmap, or
summing spectra over a time window), you can project the per-scan data onto a
shared grid. This is lossy by construction (it reintroduces the zeros and merges
points), so it is a deliberate choice, not the default.

Choosing precision
------------------

Two different "precisions" apply, and conflating them is the trap:

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Use
     - Default
     - Why
   * - Per-scan m/z labels (``mass_labels``)
     - 4 decimals
     - Reporting precision on the raw per-scan values; reflects ~ppm mass
       accuracy. There is no shared axis, so this rounding creates no zeros and
       merges nothing.
   * - Opt-in grid projection
     - 0.01 Da
     - A common HRMS-profile grid. Coarse enough to absorb most calibration
       drift, fine enough to roughly preserve resolution.

Never apply nominal mass (``prec=0``) to a high-resolution grid; it collapses the
spectrum to integer m/z. And never use a fine grid such as 0.0001 Da as the grid
spacing; that is the catastrophic-zeros case above. Four decimals belongs to the
per-scan labels, not to the grid.

A note on centroids
-------------------

Centroids are sparse peaks, so a histogram onto a shared grid is reasonable, and
combining peaks across scans onto a common axis is a normal operation (a
consensus spectrum, a centroid EIC). But gridding still **quantizes each peak's
m/z to the bin width**, and the default nominal precision would round
high-resolution peaks to integer mass, merging real peaks. So for centroids,
prefer the raw per-scan peak lists, and treat any binning as an explicit choice
with an appropriate (non-nominal) precision.
