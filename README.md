# rainbow
[![PyPI version](https://badge.fury.io/py/rainbow-api.svg)](https://badge.fury.io/py/rainbow-api)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/evanyeyeye/rainbow.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/evanyeyeye/rainbow/context:python)

*rainbow* provides programmatic access to the raw data encoded in chromatography and mass spectrometry binary files. This library supports the following vendors and detectors:

**Agilent .D**
* `.uv` - UV spectrum (supports incomplete files)
* `.ch` - UV, FID, CAD, and ELSD channels
* `.ms` - MS (supports incomplete files)
* `MSProfile.bin` - HRMS

**Waters .raw**
* `CHRO` - CAD and ELSD, as well as miscellaneous analog data
* `FUNC` - UV and MS 

There is documentation for *rainbow* that also details the structure of each file format.

## Installation

```
pip install rainbow-api
```

## Usage

The easiest way to get started is to give *rainbow* a directory path:
```python
import rainbow as rb
datadir = rb.read("some_path.D")
```

The raw data is contained in numpy arrays that are attributes of the `datadir` DataDirectory object. Users may find the following particularly useful:
* `datadir.xlabels` - retention times
* `datadir.ylabels` - wavelengths, mz values, etc.
* `datadir.data` - absorbances, intensities, etc. 

There is a tutorial available. There are also example scripts for basic tasks. 

## Contents
* `rainbow/` contains the code of the Python library.
* `docs/` contains code for generating documentation. To build documentation locally, you will need to install the `sphinx` and `sphinx-rtd-theme` packages. Then, move to the `docs/` directory and run `make html`. The docpages will be generated under `docs/_build`. 
* `tests/` contains unit tests for the library. These can be run with `python -m unittest`. 