"""
Build hook for the optional compiled accelerators.

Project metadata lives in ``pyproject.toml``; this file exists only to compile
the optional Cython extensions that speed up Agilent decoding (the ``.uv`` and
``.ch`` delta loops and the MassHunter ``MSProfile.bin`` run-length decode).
Each extension is marked ``optional`` so that a missing compiler (or missing
Cython) never breaks installation -- the package falls back to pure Python.
"""
import os

from setuptools import setup, Extension

# Optional compiled accelerators, keyed by module name -> Cython source.
_EXTENSIONS = {
    "rainbow.agilent._uvdelta": "rainbow/agilent/_uvdelta.pyx",
    "rainbow.agilent._msprofile": "rainbow/agilent/_msprofile.pyx",
    "rainbow.agilent._chdelta": "rainbow/agilent/_chdelta.pyx",
}

ext_modules = []
# Only compile an accelerator if both Cython and its source are present. A
# source is missing only from a malformed sdist; guarding here means such a
# build degrades to pure Python instead of failing outright.
_sources = {name: pyx for name, pyx in _EXTENSIONS.items() if os.path.exists(pyx)}
if _sources:
    try:
        from Cython.Build import cythonize

        ext_modules = cythonize(
            [Extension(name, [pyx], optional=True)
             for name, pyx in _sources.items()],
            compiler_directives={"language_level": "3"},
        )
    except ImportError:
        # Cython unavailable at build time: install as pure Python.
        pass

setup(ext_modules=ext_modules)
