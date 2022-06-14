# Rainbow

*a web application for analyzing chromatography data*

by Eugene Kwan and Evan Shi

## Installation 

Clone the repository and enter the main directory.
```
git clone git@github.com:evanyeyeye/rainbow.git
cd rainbow
```

Create and activate a virtual environment. 
```
virtualenv venv
source venv/bin/activate
```

Install the required dependencies.
```
pip install -r requirements.txt
```

Update your PYTHONPATH by adding this line to your .bash_profile or .bashrc file. 
```
export PYTHONPATH="$PYTHONPATH:(YOUR CURRENT WORKING DIRECTORY)"
```

## Testing

```
cd test
python test_agilent.py
```

## Docs

```
cd docs
make html
```

The docpages are generated under the docs/_build directory. 

## TODO: Installation for Webapp

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
