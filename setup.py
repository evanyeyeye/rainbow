"""
Build hook for the optional compiled accelerator.

Project metadata lives in ``pyproject.toml``; this file exists only to compile
the optional Cython extension that speeds up Agilent .uv decoding. The
extension is marked ``optional`` so that a missing compiler (or missing Cython)
never breaks installation -- the package falls back to pure Python.
"""
import os

from setuptools import setup, Extension

_PYX = "rainbow/agilent/_uvdelta.pyx"

ext_modules = []
# Only attempt to compile the accelerator if both Cython and the source are
# present. The source is missing only from a malformed sdist; guarding here
# means such a build degrades to pure Python instead of failing outright.
if os.path.exists(_PYX):
    try:
        from Cython.Build import cythonize

        ext_modules = cythonize(
            [
                Extension(
                    "rainbow.agilent._uvdelta",
                    [_PYX],
                    optional=True,
                )
            ],
            compiler_directives={"language_level": "3"},
        )
    except ImportError:
        # Cython unavailable at build time: install as pure Python.
        pass

setup(ext_modules=ext_modules)
