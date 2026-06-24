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
release = '1.0'

language = 'en'
master_doc = 'index'
source_suffix = '.rst'

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