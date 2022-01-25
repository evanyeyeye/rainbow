# AUTO GENERATED FILE - DO NOT EDIT

filePicker <- function(id=NULL, file_map=NULL, multiple_selection_allowed=NULL, root_folder_id=NULL, selected_files=NULL) {
    
    props <- list(id=id, file_map=file_map, multiple_selection_allowed=multiple_selection_allowed, root_folder_id=root_folder_id, selected_files=selected_files)
    if (length(props) > 0) {
        props <- props[!vapply(props, is.null, logical(1))]
    }
    component <- list(
        props = props,
        type = 'FilePicker',
        namespace = 'rainbow_components',
        propNames = c('id', 'file_map', 'multiple_selection_allowed', 'root_folder_id', 'selected_files'),
        package = 'rainbowComponents'
        )

    structure(component, class = c('dash_component', 'list'))
}
