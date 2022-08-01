project = 'rainbow'
copyright = '2022, Evan Shi and Eugene Kwan'
author = 'Evan Shi and Eugene Kwan'
release = '1.0'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode'
]

autosummary_generate = True
add_module_names = False
html_show_sourcelink = False
autodoc_member_order = "bysource"
autodoc_default_options = {
    'members': True, 
    'undoc-members': True, 
    'show-inheritance': True, 
    'inherited-members': True
}

master_doc = 'index'
source_suffix = '.rst'
language = 'en'

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# -- Extension configuration -------------------------------------------------

from sphinx.ext.napoleon.docstring import GoogleDocstring

def parse_attributes_section(self, section):
    return self._format_fields('Attributes', self._consume_fields())

GoogleDocstring._parse_attributes_section = parse_attributes_section

def patched_parse(self):
    self._unpatched_parse()
    
GoogleDocstring._unpatched_parse = GoogleDocstring._parse
GoogleDocstring._parse = patched_parse