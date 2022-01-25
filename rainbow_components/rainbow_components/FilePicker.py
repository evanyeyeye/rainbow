# AUTO GENERATED FILE - DO NOT EDIT

from dash.development.base_component import Component, _explicitize_args


class FilePicker(Component):
    """A FilePicker component.


Keyword arguments:

- id (string; optional):
    The ID used to identify this component in Dash callbacks.

- file_map (dict; optional):
    JSON-style dictionary containing file tree.

- multiple_selection_allowed (boolean; default True):
    Whether we are allowed to select multiple files.

- root_folder_id (string; default ''):
    The id of the root folder.

- selected_files (list; optional):
    Selected files."""
    @_explicitize_args
    def __init__(self, id=Component.UNDEFINED, multiple_selection_allowed=Component.UNDEFINED, selected_files=Component.UNDEFINED, root_folder_id=Component.UNDEFINED, file_map=Component.UNDEFINED, **kwargs):
        self._prop_names = ['id', 'file_map', 'multiple_selection_allowed', 'root_folder_id', 'selected_files']
        self._type = 'FilePicker'
        self._namespace = 'rainbow_components'
        self._valid_wildcard_attributes =            []
        self.available_properties = ['id', 'file_map', 'multiple_selection_allowed', 'root_folder_id', 'selected_files']
        self.available_wildcard_properties =            []
        _explicit_args = kwargs.pop('_explicit_args')
        _locals = locals()
        _locals.update(kwargs)  # For wildcard attrs
        args = {k: _locals[k] for k in _explicit_args if k != 'children'}
        for k in []:
            if k not in args:
                raise TypeError(
                    'Required argument `' + k + '` was not specified.')
        super(FilePicker, self).__init__(**args)
