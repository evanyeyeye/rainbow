# Rainbow

*a web app for analyzing chromatography data*
Eugene Kwan and Evan Shi

# Installation

- create Python virtual environment called `dash` with python, pandas, dash, dash-bootstrap-components, and virtualenv
- ensure node is installed (download from website)
- go into `rainbow_components` and run `npm install`
- `npm start` inside `rainbow_components` to try the React file picker on its own
- code is in `src/lib/components`
- to install the react component into dash, start by creating a special virtual environment: `virtualenv venv`
- `conda deactivate` if a Python environment is active
- `source venv/bin/activate` in the `rainbow_components` folder
- `pip install -r requirements.txt`
- `npm run build:backends`
- `npm run build:js`
- `deactivate`
- `conda activate dash` (ensure dash is installed in this virtual environment!)
- `pip install .`
- to run the widgets, go to `rainbow` and run `rainbow.py` (file picker) or `rainbow2.py (integration widget)
