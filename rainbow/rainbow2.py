import dash
from dash import html, dcc
from dash import dash_table as dt
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from dash.dash_table.Format import Format, Scheme, Trim
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import json

# sequence of colors to use for peaks
PEAK_COLORS = px.colors.qualitative.Plotly
#PEAK_COLOR_NAMES = ["blue", "red", "green", "purple", "orange", "cyan", "coral", "lime", "pink", "gold"]
print("---")

# represents a peak
class Peak():
	def __init__(self, name="", t_min=0, t_max=0, color="#000000"):
		self.name = name
		self.t_min = t_min
		self.t_max = t_max
		self.color = color

	def __str__(self):
		return json.dumps(self.__dict__)

	def integrate(self, df):
		query_df = df.query(f"{self.t_min} <= time <= {self.t_max}")
		max_index = query_df.intensity.argmax()
		self.max_time = float(query_df.time.iloc[max_index])
		self.max_intensity = float(query_df.intensity.iloc[max_index])
		self.area = float(query_df.intensity.sum())
		self.area_percent = float(self.area * 100.0 / df.intensity.sum())
		return query_df

	@staticmethod
	def from_json(json_string):
		peak = Peak()
		peak.__dict__ = json.loads(json_string)
		return peak

# load some dummy data
df = pd.read_csv("/Users/ekwan/research/rainbow/data/round2/A2Rd2_01/Export_58838.arw", skiprows=4, header=None)
df.columns=["time","intensity"]

# redraws the chromatogram
def get_figure(peaks=[]):
	figure = go.Figure()
	graph = go.Scatter(x=df.time, y=df.intensity, mode='lines',
		               line={"width":1, "color":"#000000"},
		               hovertemplate=
		               "%{x:.2f} min" +
		               "<extra></extra>")
	figure.add_trace(graph)

	for i,peak in enumerate(peaks):
		name = peak.name
		query_df = peak.integrate(df)
		color = peak.color
		graph = go.Scatter(x=query_df.time, y=query_df.intensity, mode='lines',
	               line={"width" : 3, "color" : color},
	               hovertemplate=
	               	f"%{{x:.2f}} min (Peak {i+1}, {name})" +
	               	"<extra></extra>")
		figure.add_trace(graph)
	

	figure.update_layout(showlegend=False, xaxis_title="time (min)",
		                 yaxis_title="intensity")
	#figure.update_yaxes(fixedrange=True)
	return figure

# define the peak table
columns = [
	{"name" : " ", "id" : "color", "editable" : False,
	 "type" : "text", "presentation" : "dropdown",
	},

	{"name" : "name", "id" : "name", "editable" : True,
	 "type" : "text",
	 "on_change" : {"action" : "coerce", "failure" : "default"},
	 "validation" : {"default" : "string"},
	},

	{"name" : "start (min)", "id" : "start (min)", "editable" : True,
	 "type" : "numeric", "format" : Format(precision=3, scheme=Scheme.fixed),
	 "on_change" : {"action" : "coerce", "failure" : "reject"},
	 "validation" : {"default" : "number"},
	},

	{"name" : "end (min)", "id" : "end (min)", "editable" : True,
	 "type" : "numeric", "format" : Format(precision=3, scheme=Scheme.fixed),
	 "on_change" : {"action" : "coerce", "failure" : "reject"},
	 "validation" : {"default" : "number"},
	},

	{"name" : "area%", "id" : "area%", "editable" : False,
	 "type" : "numeric", "format" : Format(precision=2, scheme=Scheme.fixed)
	},
]

peaks_table = html.Div(
				dt.DataTable(id="peaks_table", columns=columns, 
					         style_header={"fontFamily" : "sans-serif"},
					         style_cell_conditional = [
					           {"if": {"column_id":"color"},
					            "width":"20px"},
					           {"if": {"column_id":"name"},
					            "width":"200px"},
					           {"if": {"column_id":"name"},
					            "textAlign":"left", "paddingLeft":"10px"}
					         ],
					         row_deletable=True
					        ),
				style={"width":500, "marginLeft":20},
			  )

# generate data for the datatable
def get_peak_table_data(peaks):
	peaks_table_data = []
	styler = []
	for i,peak in enumerate(peaks):
		# for the peak properties
		temp_dict = {}
		temp_dict["color"] = " "
		temp_dict["name"] = peak.name
		temp_dict["start (min)"] = round(peak.t_min,4)
		temp_dict["end (min)"] = round(peak.t_max,4)
		temp_dict["area%"] = peak.area_percent
		peaks_table_data.append(temp_dict)

		# for the color swatch
		styler.append({
			"if" : {"row_index" : i,
			        "column_id" : "color"},
			"backgroundColor" : peak.color,
			}
		)
		styler.append({
			"if" : {"column_id" : "color",
					"row_index" : i,
			        "state" : "selected"},
			"backgroundColor" : peak.color,
			})
		styler.append({
     		"if" : {"state" : "active"},
     		"backgroundColor" : "#F5F5F5",
     		"border" : "2px solid black",
     		"color" : "black",
     		"font-weight" : "bold",
		})
		styler.append({
			"if" : {"column_id" : "color",
					"row_index" : i,
			        "state" : "active"},
			"backgroundColor" : peak.color,
		})
		

	# for column font
	styler.append({
		"if" : {"column_id" : "name"},
		"font-family" : "sans-serif",})
	return peaks_table_data, styler

# sets up the app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, "app.css"])

app.layout = html.Div(
    children=[
   		dcc.Graph(id="chromatogram", figure=get_figure(),
   			      config={"displayModeBar": False, "showTips" : False, "scrollZoom" : False}),
   		peaks_table,
    	#html.P(id="drag"),
    	dcc.Store(id="peaks_store", data=[]),
    ],
)

@app.callback(
	Output("chromatogram", "figure"),
	Output("peaks_store", "data"),
	Output("peaks_table", "data"),
	Output("peaks_table", "style_data_conditional"),
	Output("peaks_table", "selected_cells"),
	Output("peaks_table", "active_cell"),
	Input("chromatogram", "relayoutData"),
	Input("peaks_table", "data"),
	State("peaks_store", "data"),
)
def handle_chromatogram_events(relayoutData, peaks_table_data, peaks_store_data):
	try:
		trigger = dash.callback_context.triggered[0]["prop_id"]
		print(trigger)
	except:
		raise PreventUpdate

	# reconstitute the cached peaks
	peaks = [ Peak.from_json(s) for s in peaks_store_data ]

	if trigger is None or trigger == ".":
		raise PreventUpdate
	elif trigger == "chromatogram.relayoutData":
		if "xaxis.range[0]" not in relayoutData:
			raise PreventUpdate

		# this is a drag event, so create a new peak
		t_min = relayoutData["xaxis.range[0]"]
		t_max = relayoutData["xaxis.range[1]"]
		color = PEAK_COLORS[len(peaks) % len(PEAK_COLORS)]
		existing_names = [ p.name for p in peaks ]
		i = len(peaks)+1
		while True:
			name = f"Peak {i}"
			if name not in existing_names:
				break
			i += 1 
		new_peak = Peak(name, t_min, t_max, color)
		peaks.append(new_peak)
	elif trigger == "peaks_table.data":
		# handle row deletions
		if len(peaks_table_data) < len(peaks):
			new_peaks = []
			names_to_include = [ p["name"] for p in peaks_table_data ]
			for p in peaks:
				name = p.name
				if name not in names_to_include:
					continue
				t_min, t_max = p.t_min, p.t_max
				color = PEAK_COLORS[len(new_peaks) % len(PEAK_COLORS)]
				new_peak = Peak(name, t_min, t_max, color)
				new_peaks.append(new_peak)
			peaks = new_peaks

		# handle table edits
		else:
			valid = True
			for peak_dict,peak in zip(peaks_table_data,peaks):
				# validate inputs
				new_name = peak_dict["name"].strip()
				if len(new_name) == 0:
					valid = False

				t_min, t_max = peak_dict["start (min)"], peak_dict["end (min)"]
				if t_max - t_min < 0.001 or t_max < 0 or t_min < 0:
					valid = False

			# check for duplicate names
			name_set = { entry["name"] for entry in peaks_table_data }

			if len(name_set) < len(peaks_table_data):
				valid = False

			# validated, so update peaks
			if valid:
				for peak_dict, peak in zip(peaks_table_data, peaks):
					new_name = peak_dict["name"].strip()
					t_min, t_max = peak_dict["start (min)"], peak_dict["end (min)"]
					peak.name = new_name
					peak.t_min = t_min
					peak.t_max = t_max

	else:
		raise ValueError(f"unrecognized trigger: {trigger}")

	# update the figure, cached peaks, and peak table
	figure = get_figure(peaks)
	peaks_json = [ str(peak) for peak in peaks ]
	peaks_table_data, styler = get_peak_table_data(peaks)
	return figure, peaks_json, peaks_table_data, styler, [], None

# run the app
if __name__ == "__main__":
    app.run_server(debug=True)