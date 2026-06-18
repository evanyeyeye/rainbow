# rainbow
[![PyPI](https://img.shields.io/pypi/v/rainbow-api)](https://pypi.org/project/rainbow-api)
[![Documentation Status](https://readthedocs.org/projects/rainbow-api/badge/?version=latest)](https://rainbow-api.readthedocs.io/en/latest/?badge=latest)
[![PyPI - Downloads](https://static.pepy.tech/badge/rainbow-api)](https://pypi.org/project/rainbow-api)

*rainbow* provides programmatic access to the raw data encoded in chromatography and mass spectrometry binary files. This library supports the following vendors and detectors:

**Agilent .D**
* `.uv` - UV spectrum (supports incomplete files)
* `.ch` - UV, FID, CAD, and ELSD channels
* `.ms` - MS (supports incomplete files)
* `MSProfile.bin` - HRMS and ICP-MS profile spectrum (parse with `hrms=True`)
* `MSPeak.bin` - centroid (peak-picked) spectrum (parse with `centroid=True`)

**Agilent .dx (OpenLab CDS)**
* `.UV` - DAD spectrum
* `.CH` - single-wavelength UV/DAD signals
* `.IT` - instrument telemetry, as analog data (parse with `telemetry=True`)

**Waters .raw**
* `CHRO` - CAD and ELSD, as well as miscellaneous analog data
* `FUNC` - UV and MS 

There is [documentation](http://rainbow-api.readthedocs.io/) for *rainbow* that also details the structure of each [binary file format](https://rainbow-api.readthedocs.io/en/latest/formats.html).

## Installation

```
pip install rainbow-api
```

Prebuilt wheels include an optional compiled accelerator (see
[Performance](#performance)); installation never requires a compiler, and
*rainbow* works the same with or without it.

## Usage

The easiest way to get started is to give *rainbow* a directory path. Assume that we have a directory `mydata.D` that contains a binary file `DAD1.uv` with UV data. 

```python
import rainbow as rb
datadir = rb.read("mydata.D")
datafile = datadir.get_file("DAD1A.uv")
```

Here, the `datadir` DataDirectory object contains a DataFile object for `DAD1A.uv`. 

*rainbow* normally infers the vendor from the path suffix (`.D`/`.dx` for Agilent, `.raw` for Waters). A directory whose name lacks that suffix is identified from its contents instead, so renamed datasets still parse. To force a parser explicitly, pass `format`:

```python
datadir = rb.read("Noscapine 3", format="waters")
```

The raw UV data is contained in numpy arrays that are attributes of `datafile`. Users may find the following particularly useful:
* `datafile.xlabels` - 1D numpy array with retention times
* `datafile.ylabels` - 1D numpy array with wavelengths
* `datafile.data` - 2D numpy array with absorbances 

There is a [tutorial](https://rainbow-api.readthedocs.io/en/latest/tutorial.html) available. There are also example [snippets](https://rainbow-api.readthedocs.io/en/latest/examples.html) for basic tasks. Or just check out the full [API](https://rainbow-api.readthedocs.io/en/latest/api.html). 

## Performance

A few decode loops dominate parsing time: each reads a long sequence of
delta- or run-length-encoded values into a running accumulator, which is
inherently sequential and cannot be vectorized with NumPy. *rainbow* ships
optional compiled extensions (built with Cython) that run these inner loops in
C, roughly **100&times; faster** while producing bit-identical results:

* `rainbow/agilent/_uvdelta.pyx` &mdash; the Agilent diode-array (DAD) `.uv` decode.
* `rainbow/agilent/_chdelta.pyx` &mdash; the Agilent `.ch` channel (CAD/ELSD/UV) decode.
* `rainbow/agilent/_msprofile.pyx` &mdash; the MassHunter `MSProfile.bin` run-length decode.

The accelerators are entirely optional:

* Prebuilt wheels on PyPI already include them, so `pip install rainbow-api`
  gives you the fast path with no compiler needed.
* If you install from source without a compiler (or without Cython), the build
  simply skips the extensions and *rainbow* falls back to pure-Python decoders
  with identical output. You can check whether a given accelerator is active
  with, e.g., `rainbow.agilent.chemstation._uvdelta_fast is not None`
  (likewise `_chdelta_fast` and `rainbow.agilent.masshunter._msprofile_fast`).

## Contents
* `rainbow/` contains the code of the Python library.
* `docs/` contains code for generating documentation. To build documentation locally, you will need to install the `sphinx` and `sphinx-rtd-theme` packages. Then, move to the `docs/` directory and run `make html`. The docpages will be generated under `docs/_build`. 
* `tests/` contains unit tests for the library. These can be run with `pytest` from the repository root (install the test dependency with `pip install -e .[test]`). 

For development, an editable install (`pip install -e .`) compiles the optional
accelerator in place if a C compiler and Cython are available; otherwise the
pure-Python fallback is used. The parity between the two paths is checked by
`tests/test_accelerator.py`.
