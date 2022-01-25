# AUTO GENERATED FILE - DO NOT EDIT

export filepicker

"""
    filepicker(;kwargs...)

A FilePicker component.

Keyword arguments:
- `id` (String; optional): The ID used to identify this component in Dash callbacks.
- `file_map` (Dict; optional): JSON-style dictionary containing file tree.
- `multiple_selection_allowed` (Bool; optional): Whether we are allowed to select multiple files
- `root_folder_id` (String; optional): The id of the root folder.
- `selected_files` (Array; optional): Selected files.
"""
function filepicker(; kwargs...)
        available_props = Symbol[:id, :file_map, :multiple_selection_allowed, :root_folder_id, :selected_files]
        wild_props = Symbol[]
        return Component("filepicker", "FilePicker", "rainbow_components", available_props, wild_props; kwargs...)
end

