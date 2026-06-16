"""
Build hook for the optional compiled accelerator.

Project metadata lives in ``pyproject.toml``; this file exists only to compile
the optional Cython extension that speeds up Agilent .uv decoding. The
extension is marked ``optional`` so that a missing compiler (or missing Cython)
never breaks installation -- the package falls back to pure Python.
"""
from setuptools import setup, Extension

ext_modules = []
try:
    from Cython.Build import cythonize

    ext_modules = cythonize(
        [
            Extension(
                "rainbow.agilent._uvdelta",
                ["rainbow/agilent/_uvdelta.pyx"],
                optional=True,
            )
        ],
        compiler_directives={"language_level": "3"},
    )
except ImportError:
    # Cython unavailable at build time: install as pure Python.
    pass

setup(ext_modules=ext_modules)
