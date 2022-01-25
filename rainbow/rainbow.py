import dash
from dash import html, dcc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import json, copy
from rainbow_components import FilePicker
import filemap as fm

file_map = fm.initialize("/Users/ekwan/research/rainbow/data")

app = dash.Dash(__name__)

app.layout = html.Div(
    children=[
        FilePicker(id="picker", file_map=file_map, multiple_selection_allowed=True),
        html.P(id="selection", children="selection: none"),
        dcc.Store(id="file_map", data=file_map),
    ],
    style={"height":500,"width":800}
)

@app.callback(
    Output("selection", "children"),
    Input("picker", "selected_files"),
)
def update_selection(selected_files):
    if selected_files and selected_files != "none":
        return f"selection: {selected_files}"
    raise PreventUpdate

# open the specified folder
@app.callback(
    Output("picker", "file_map"),
    Output("file_map", "data"),
    Input("picker", "root_folder_id"),
    State("file_map", "data"),
)
def update_root(root_folder_id, file_map):
    if not root_folder_id or root_folder_id == "none":
        raise PreventUpdate
    fm.set_root_folder(file_map, root_folder_id)
    return file_map, file_map

if __name__ == "__main__":
    app.run_server(debug=True)
