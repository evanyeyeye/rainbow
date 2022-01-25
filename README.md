# Rainbow

*a web app for analyzing chromatography data*
Eugene Kwan and Evan Shi

# Installation

- ensure node is installed
- `npm start` inside `rainbow_components` to try the React file picker on its own
- code is in `src/lib/components`
- to compile the react component for Dash, `conda deactivate` if a Python environment is active
- `source venv/bin/activate` in the `rainbow_components` folder
- `npm run build:backends`
- `npm run build:js`
- `deactivate`
- `conda activate dash` (ensure dash is installed in this virtual environment!)
- `pip install .`
- to run the widgets, go to `rainbow` and run `rainbow.py` (file picker) or `rainbow2.py (integration widget)
