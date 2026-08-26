"""
Sphinx Configuration

"""
import os
import sys

sys.path.insert(0, os.path.abspath('../..'))

################################
# General Documentation Config #
################################

project = 'rainbow'
copyright = '2022, Evan Shi and Eugene Kwan'
author = 'Evan Shi and Eugene Kwan'
# Read the version rather than restating it, so this cannot drift from
# pyproject.toml. Read the Docs installs only docs/requirements.txt, not the
# package itself, so the metadata lookup fails there and pyproject has to be
# read directly; falling through to an empty string would put the version of
# the published documentation at "".
try:
    from importlib.metadata import version as _version
    release = _version("rainbow-api")
except Exception:                       # not installed, e.g. on Read the Docs
    import os
    import re
    _pyproject = os.path.join(
        os.path.dirname(__file__), '..', '..', 'pyproject.toml')
    with open(_pyproject, encoding='utf-8') as _f:
        release = re.search(r'^version\s*=\s*"([^"]+)"', _f.read(),
                            re.MULTILINE).group(1)

language = 'en'
master_doc = 'index'
# The rainbow.debug format catalogue is written in Markdown, so both are
# parsed. myst_heading_anchors gives every heading an anchor, which is what
# the catalogue's own section cross-links point at.
source_suffix = {'.rst': 'restructuredtext', '.md': 'markdown'}
myst_heading_anchors = 3

# Number figures (Fig. 1, Fig. 2, ...) so the text can cross-reference them by
# number with :numref: instead of "the figure below".
numfig = True

templates_path = ['_templates']
exclude_patterns = ['Thumbs.db', '.DS_Store']
html_theme = 'sphinx_rtd_theme'
html_favicon = '_static/favicon.ico'
html_static_path = ['_static']
html_css_files = ['custom.css']

add_module_names = False
html_show_sourcelink = False

extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.mathjax'
]
 
#######################################
# Autosummary & Autodoc Configuration #
#######################################

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_default_options = {
    'members': True, 
    'undoc-members': True, 
    'show-inheritance': True, 
    'inherited-members': True
}

from sphinx.ext.napoleon.docstring import GoogleDocstring

def parse_attributes_section(self, section):
    return self._format_fields('Attributes', self._consume_fields())

GoogleDocstring._parse_attributes_section = parse_attributes_section

def patched_parse(self):
    self._unpatched_parse()
    
GoogleDocstring._unpatched_parse = GoogleDocstring._parse
GoogleDocstring._parse = patched_parse